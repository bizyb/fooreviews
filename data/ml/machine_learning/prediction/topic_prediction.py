import csv
from datetime import timedelta
import fooreviews.models as f_models
import ml.machine_learning.modeling.topic_modeling as tm
import ml.models as m_models
import numpy as np
from scipy import stats
from time import time
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class TopicPrediction(tm.TopicModeling):
	'''
	Predicts LDA topics using the trained model for given
	domain and subdomain.
	Our approach to getting the predicted topics is as follows:
		1. Get the predict topics for each document bow 
		2. Get the prediction with the highest probability for each 
			document whose predicted topic_num is not incoherent
		3. Get a frequency distribution of the topic numbers run 
			a regression modeling to predict new probabilities
		4. Rank the regression-modeled frequency-probability pair
	'''
	def __init__(self, **kwargs):
		super(TopicPrediction, self).__init__(**kwargs)
		self.clear_db = kwargs.get('clear_db')
		self.lda_model = self.train_lda_model()
		self.pred_exists = self._pred_exists()
		self.incoherent = []
		self.corpus = []
		if not self.pred_exists:
			self.incoherent = self._get_inchorent_topic_nums()
			self.corpus = self._get_lda_bow(prediction=True)
		self.freq_mean_fin = {}
		self.final_avged = {}

	def _pred_exists(self):
		params = {'product__frsku':self.frsku}
		EXISTS = m_models.PredictedLDATopic.objects.filter(**params).exists()
		return EXISTS

	def _get_inchorent_topic_nums(self):
		params = {
			'domain__domain': self.domain,
			'domain__subdomain': self.subdomain,
			'coherent': False,
		}
		topic_set = m_models.LDATopic.objects.filter(**params)
		topic_num_list = [obj.topic_num for obj in topic_set]
		return topic_num_list

	def stage_prediction(self):
		'''
		Run the prediciton asynchronously.

		The gensim prediction uses a random seed value whenever it 
		predicts document topics. Therefore, we should iterate the
		predictions a good number of times and average the results.

		Order of calls:
		1. async calls _predict
			a. _predict calls other helper functions
		2. async calls _final_pred_avg to average iterated results
		3. async calls _rank_predictions
			a. _rank_predictions calls _regression to get the model
			b. _rank_predictions calls _get_regression_probs with the model
			b. _rank_predictions constructs the final dictionary for db 
				population
		'''

		if not self.pred_exists or self.clear_db:
			# iteration time scales linearly--15 seconds per 10 iterations
			ITERATIONS = 1000 #
			then = time()
			msg = 'Initiating LDA topic prediction for FRSKU={}\n'
			msg = msg.format(self.frsku)
			logger.info(msg)
			for i in range(ITERATIONS):
				logger.info('Prediction iteration number {}'.format(i+1))
				self._predict()
			final_avged = self._final_pred_avg(self.freq_mean_fin)
			logger.info('Ranking predicted LDA topics')
			pred_ranked = self._rank_predictions(final_avged)
			logger.info('Done with topic ranking')
			logger.info('Saving predictions to db')
			self._predictions_to_db(pred_ranked)
			now = time()
			diff = now - then
			t = str(timedelta(seconds=diff))
			msg = 'Finished LDA topic prediciton for FRSKU={} with Iter={} '
			msg += 'Time={}\n'
			logger.info(msg.format(self.frsku, ITERATIONS, t))
		else:
			msg = 'Predicted topics already exist for FRSKU={}. '
			msg += 'Reissue command with clear_db=True'
			logger.info(msg.format(self.frsku))

	def _predict(self):
		''' 
		Get predicted topics for positive and negative sentiment 
		groups.
		'''	
		# get raw predictions
		logger.info('Getting raw predictions')
		raw_predictions = self._get_raw_predictions(self.corpus)

		# group the predictions by their topic_num
		logger.info('Grouping raw predictions')
		params = {'pred_list': raw_predictions}
		predictions_grouped, count = self._group_predictions(**params)

		# generate a frequency-mean probability for each group
		logger.info('Calculating group frequency and mean probability')
		freq_mean = self._freq_mean(predictions_grouped, count)

		# append group averages to a master dictionary
		logger.info('Caching group frequency and average probability \n')
		self._append_freq_mean(freq_mean, self.freq_mean_fin)

	def _get_raw_predictions(self, corpus_bow):
		'''
		Topic prediction is done at the document-level. Gensim's 
		get_document_topics() returns a list with tuples as elements.
		Each tuple is composed of two elements--predicted topic number 
		at index=0 and probability at index=1.
		E.g. (abridged:
			[(0, 0.01553846153846155),
			(1, 0.030923076923076932),
			(7, 0.061692307692307713),
			(10, 0.015538461538461543),
			(12, 0.030923076923076932),
			(13, 0.030923076923076932),
			...]
		'''
		raw_predictions = []
		if self.lda_model:
			for doc_corpus in corpus_bow:
				predictions = self.lda_model.get_document_topics(doc_corpus)
				predictions_list = self._sort_predictions(predictions)
				highest = ()
				INDEX = -1
				for i in range(len(predictions_list)):
					highest = predictions_list[i]
					topic_num = highest[0]
					if topic_num not in self.incoherent:
						INDEX = i
						break
					else:
						highest = ()
				if highest:
					# add all valid predictions
					valid_preds = self._adjacent_probs(INDEX, predictions_list)
					raw_predictions.extend(valid_preds)
			if raw_predictions:
				sorted_predictions = self._sort_predictions(raw_predictions)
				return sorted_predictions
		else:
			msg = 'Failed to load a trained LDA model from disk'
			logger.debug(msg)

	def _sort_predictions(self, pred_list, col_num=1, regression_probs=False):
		'''
		Sort a list of 2-column tuples on the specified column in descending
		order and convert the resulting numpy array to a nested list.
		'''
		COL_NUM = col_num
		pred_array = np.array(pred_list)
		pred_array = pred_array[np.argsort(-pred_array[:,COL_NUM])]
		reformed_list = []
		for p in pred_array:
			topic_num = int(p[0])
			prob = p[1]
			to_append = [topic_num, prob]
			if regression_probs:
				freq = int(p[1])
				prob_old = p[2]
				prob_new = p[3]
				to_append = [topic_num, freq, prob_old, prob_new]
			reformed_list.append(to_append)
		return reformed_list


	def _adjacent_probs(self, index, predictions):
		''' 
		Return all predictions whose topic_nums are not incoherent 
		and whose probabilities are equal to the highest valid prediction. 
		'''
		# use a defined precision; this is the default in the probs
		PRECISION = 17
		highest_prop = round(predictions[index][1], PRECISION)
		valid_preds = [predictions[index]]
		for i in range(len(predictions)):
			try:
				pred = predictions[index+i]
				topic_num = pred[0]
				prob = round(pred[1],PRECISION) 
				if prob == highest_prop:
					if topic_num not in self.incoherent:
						valid_preds.append(pred)
			except IndexError:
				pass
		return valid_preds

	
	def _group_predictions(self, pred_list=[]):
		'''
		Group predicted topic probabilities by by their topic numbers.
		E.g. [[topic_num_x, a], [topic_num_y, b], [topic_num_x, c]]
				to
			{topic_num_x: [a, b, c], topic_num_y: [b]}
		'''
		pred_dict = {}
		count = 0
		for pred in pred_list:
			topic_num = pred[0]
			prob = pred[1]
			if topic_num in pred_dict:
				pred_dict[topic_num].append(prob)
			else:
				pred_dict[topic_num] = [prob]
			count += 1
		return pred_dict, count

	def _freq_mean(self, pred_dict, total_pred_count):
		'''
		Calculate the frequency and weighted average for each group of 
		probabilities. To do so, take the arithmetic mean of the probabilities 
		for each group and normalize it by weighting the resulting value using
		the group's weighting factor.
		E.g. {topic_num: [a, b, c,..]}, where a,b,c, etc. are the probablities

		'''
		freq_mean_dict = {}
		for topic_num, probs in pred_dict.items():
			freq = len(probs)
			w_factor = freq/float(total_pred_count)
			group_avg =  sum(probs)/float(freq)
			w_avg = w_factor*group_avg
			freq_mean_dict[topic_num] = [freq, w_avg]
		return freq_mean_dict

	def _append_freq_mean(self, freq_mean_dict, master_dict):
		'''
		Append a list of [freq, mean] by topic_num to a master dictionary.

		We're not returning anything because we're working with references
		to global variables.
		'''
		for topic_num, freq_mean_list in freq_mean_dict.items():
			if topic_num in master_dict:
				master_dict[topic_num].append(freq_mean_list)
			else:
				master_dict[topic_num] = [freq_mean_list]

	def _final_pred_avg(self, master_dict):
		'''
		Get the final frequency and probability averages from all 
		the iterations.
		'''
		averaged_dict = {}
		for topic_num, freq_mean_nested in master_dict.items():
			freq_total = 0
			prob_total = 0
			count = 0
			for val in freq_mean_nested:
				# the size of the nested list should equal the number of 
				# iterations
				freq = val[0]
				prob = val[1]
				freq_total += freq
				prob_total += prob
				count += 1
			avg_freq = freq_total/count
			avg_prob = prob_total/float(count)
			averaged_dict[topic_num] = [avg_freq, avg_prob]
		return averaged_dict

	def _rank_predictions(self, averaged_predictions):
		'''
		Rank predictions based on the linear regression model.
		'''
		intercept, slope, r_squared = self._regression(averaged_predictions)
		pred_sorted = self._get_regression_probs(averaged_predictions, slope, \
													intercept)
		ranked = self._get_ranked_topic_nums(pred_sorted)
		return ranked 
		

	def _regression(self, data_dict):
		'''
		Perform a linear regression analysis on the predicted values.

		Each prediction is two-dimensional: we have frequency and a 
		weighted probability for each frequency.
		Assumptions and interpretations of our data:
			1. The most frequent prediction is not always the most probable 
				prediction
			2. High frequency, high probability is good
			3. Low frequency, low probability is bad 
		The linear model sould later allow us to rank our frequency-probability
		pairs without any abiguity.
		Observation after modeling:
			1. The most frequent topics are almost invariably the most probable 
			ones. We might forego using the regression model in the future 
			because the fit is almost uncanny to a point where we can simply 
			sort the iterated frequencies and get the same result as the one 
			predicted by the regression.
		'''
		
		#frequency
		x = [freq_prob[0] for topic_num, freq_prob in data_dict.items()]

		# probability 
		y = [freq_prob[1] for topic_num, freq_prob in data_dict.items()]

		# slope 
		slope, intercept, r_value, p_value, std_err = stats.linregress(x,y)

		self._regression_to_db(slope, intercept, r_value, p_value, std_err, \
								data_dict)
		return intercept, slope, r_value**2

	def _regression_to_db(self, slope, intcpt, r_value, p_value, std_err, data):
		entry = {
			'frsku': self.frsku,
			'slope': slope,
			'intercept': intcpt,
			'r_value': r_value,
			'p_value': p_value,
			'std_err': std_err,
			'data': data,
		}
		obj = m_models.LDARegression.objects.create(**entry)
		msg = 'Created new regression data with pk={} for FRSKU={}'
		msg = msg.format(obj.id, self.frsku)
		logger.info(msg)


	def _get_regression_probs(self, data_dict, slope, intercept):
		'''
		Calculate a new probability predicted by the regression model for 
		each probability in data_dict.
		'''
		master_list = []
		for topic_num, freq_prob in data_dict.items():
			freq = freq_prob[0]
			prob_old = freq_prob[1]
			prob_new = freq*slope + intercept
			reg_tuple = (topic_num, freq, prob_old, prob_new)
			master_list.append(reg_tuple)
		sorted_master_list = self._sort_predictions(master_list, \
								col_num=3, regression_probs=True)
		return sorted_master_list

	def _get_ranked_topic_nums(self, sorted_list):
		ranked_dict = {}
		for i in range(len(sorted_list)):
			topic_num = sorted_list[i][0]
			freq = sorted_list[i][1]
			rank = i + 1
			ranked_dict[topic_num] = [freq, rank]
		return ranked_dict

	def _predictions_to_db(self, ranked_dict):
		'''
		Save ranked predictions to the database.
		'''
		if self.clear_db:
			params = {'product__frsku':self.frsku}
			m_models.PredictedLDATopic.objects.filter(**params).all().delete()
		bulk = []
		for topic_num, freq_rank in ranked_dict.items():
			try:
				freq = freq_rank[0]
				rank = freq_rank[1]
				topic_lookup = {
					'domain__domain': self.domain,
					'domain__subdomain': self.subdomain,
					'topic_num': topic_num,
					'coherent': True,

				}
				topic_obj = m_models.LDATopic.objects.filter(**topic_lookup)[0]
				product_lookup = {
					'frsku': self.frsku
				}
				product_obj = f_models.Product.objects.filter(**product_lookup)[0]
				params = {
					'product': product_obj,
					'topic': topic_obj,
					'rank': rank,
					'frequency': freq
				}
				bulk.append(m_models.PredictedLDATopic(**params))
			except Exception as e:
				msg = '{}: {}'.format(type(e).__name__, e.args[0])
				logger.exception(msg)
		if bulk:
			m_models.PredictedLDATopic.objects.bulk_create(bulk)
			logger.info('Saved predictions to db')
		else:
			msg = 'Could not find any predictions to save to the database '
			msg += 'for FRSKU={}'
			logger.info(msg.format(self.frsku))

	def predictions_to_csv(self):
		'''
		(Optional, for debugging only) Output the predictions to a file.
		'''
		# TODO: dump_to_csv doesn't exist anymore; call the parent class instead
		filename = 'LDA_predicted_TOPICS_{}'.format(self.frsku)
		try:
			params = {'product__frsku':self.frsku}
			topic_set = m_models.PredictedLDATopic.objects.filter(**params)
			ch.dump_to_csv(topic_set, filename, logger)
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)
