from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import fooreviews.models as fr_models
import gensim 
import logging 
import ml.models as m_models
import pandas as pd
import os
import random
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

# output default gensim logging to terminal
logging.basicConfig(format='%(levelname)s : %(message)s', level=logging.INFO)

class TopicModeling(object):
	'''
	Performs topic modeling on a corpus of documents using gensim's 
	implementation of the Latent Dirichlet Allocation (LDA) algorithm.

	Modeling parameters:
		passes: number of iterations (higher isn't always better; need to 
				run trials to optimize it)
		chunksize: number of tokens (vocab) loaded to memory; default = 2000
		num_below: number of tokens to exclude from the corpus; usually, these 
					would be misspelled words and uncommon characters. num_below 
					works by excluding any token that has a maximum occurrence
					threshold of num_below. Type is integer.
		num_above: percent of documents wherein a certain token appears. If the 
					token appears in num_above percent of documents, it's 
					excluded from the corpus. These would usually be 
					non-informative, domain-specific terms, e.g. kitchen, fridge,
					microwave, etc. Type is float.
		keep_n: Absolute number of tokens to keep after all trimming. None means 
				keep all; Type can be float or integer (unverified).
	'''
	def __init__(self, **kwargs):
		self.frsku = kwargs.get('frsku')
		self.domain = kwargs.get('domain')
		self.subdomain = kwargs.get('subdomain')
		self.training = kwargs.get('training')
		self.product = self._get_product()
		self.domain_obj = self._get_domain_obj()
		self.MODEL_DOES_NOT_EXIST = 'Model Does Not Exist'

		# default modeling parameters
		self.TOPIC_COUNT = 0
		self.passes = 0
		self.chunksize = 0
		self.num_below = 0 
		self.num_above = 0 
		self.keep_n = None

		# model and topic names, storage directory, etc.
		self.lda_name = ''
		self.lda_topics = ''
		self.path_model = ''
		self.path_topics = ''
		self._set_lda_params()
		self._set_lda_names()

	def _set_lda_names(self):
		if self.domain_obj:
			self.lda_name = self.domain_obj.lda_model_name
			self.lda_topics = self.domain_obj.lda_topics_name
		if self.product:
			self.lda_topics = self.product.predicted_topics_name
		dir_model = 'ml/trained_models/lda/'
		dir_topics =  'ml/lda_topics/'
		if not os.path.exists(dir_model):
			os.makedirs(dir_model)
		if not os.path.exists(dir_topics):
			os.makedirs(dir_topics)
		self.path_model =  dir_model + self.lda_name
		self.path_topics = dir_topics + self.lda_topics

	def _get_domain_obj(self):
		'''
		Return ProductDomain object.
		'''
		domain_obj = None
		try:
			if self.training:
				params = {'domain': self.domain, 'subdomain':self.subdomain}
				domain_obj = m_models.TrainingDomain.objects.filter(**params)[0]
			elif self.frsku and self.product:
				domain_obj = self.product.product_domain
			self.domain = domain_obj.domain
			self.subdomain = domain_obj.subdomain
		except Exception as e:
			msg = 'Failed to get Training Domain.'.format(type(e).__name__, e.args[0])
			logger.exception(msg)
		return domain_obj

	def _get_product(self):
		'''
		Get the product object that self.frsku belongs to.
		'''
		product = None
		try:
			if self.frsku:
				product = fr_models.Product.objects.filter(frsku=self.frsku)[0]
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)
		return product


	def _set_lda_params(self):
		'''
		Set the domain/specific LDA training parameters.
		'''
		if self.domain_obj:
			self.TOPIC_COUNT = self.domain_obj.topic_count
			self.passes = self.domain_obj.iteration
			self.chunksize = self.domain_obj.chunksize
			self.num_below = self.domain_obj.minimum
			self.num_above = self.domain_obj.maximum
		else:
			msg = 'Could not set model default parameters for frsku={}. '
			msg += 'Product does not exist.'
			logger.debug(msg.format(self.frsku))

	def _get_params(self, corpus_type):
		frsku_str = 'a_review__review_raw__crawl_cache__crawl_queue__product'
		frsku_str += '_raw__product__frsku'
		params = {
			'training':  {
						't_review__review_raw__domain': self.domain,
						't_review__review_raw__subdomain': self.subdomain,
						'is_training_bow': True,
						'is_analysis_bow': False,
				},

			'analysis': {
						frsku_str: self.frsku,
						'is_training_bow': False,
						'is_analysis_bow': True, 
				},
			}
		return params.get(corpus_type)

	def _get_bow_set(self):
		if self.training:
			params = self._get_params('training')
		elif self.frsku:
			params = self._get_params('analysis')
		bow_set = m_models.BagofWords.objects.filter(**params)
		return bow_set

	def _save_trained_model(self, trained_model):
		'''
		Serialize the trained model and save it to disk.
		'''
		try:
			trained_model.save(self.path_model)
			msg = 'Saved a new LDA model with name={}'.format(self.lda_name)
			logger.info(msg)
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)

	def train_lda_model(self, new_model=False):
		'''
		Train and save an LDA model. If model does not exists, loop
		until it's trained and saved to disk.
		'''
		lda_model = None
		while True:
			try:
				msg = 'Attempting to load model at {}'.format(self.path_model)
				logger.info(msg)
				lda_model = gensim.models.LdaMulticore.load(self.path_model)
				break
			except IOError:
				if new_model:
					# new model training requested
					msg = 'Training a new model with name={}'
					logger.info(msg.format(self.lda_name))
					executor = ThreadPoolExecutor(max_workers=1)
					future_task = executor.submit(self._model_lda)
					lda_model = future_task.result()
				else:
					msg = 'Model does not exist. Call train_lda_model with '
					msg += 'new_model=True'
					logging.info(msg)
				break
			except Exception as e:
				msg = '{}: {}'.format(type(e).__name__, e.args[0])
				logger.exception(msg)
		self._topics_to_db(lda_model)		
		return lda_model

	def _get_topics(self, lda):
		'''
		Return modeled topics.
		'''
		TOPIC_COUNT = lda.num_topics
		topics = {}
		for i in range(TOPIC_COUNT):
			topic = lda.show_topic(i)
			words = []
			for w in topic:
				words.append(w[0])
			string = ' '.join(words)
			topics[i] = string
		return topics

	def _topics_to_db(self, lda):
		try:
			params = {'lda_model_name': self.lda_name}
			if not m_models.LDATopic.objects.filter(**params).exists():
				bulk = []
				topics = self._get_topics(lda)
				for topic_num, topic in topics.items():
					params = {
							'domain': self.domain_obj,
							'lda_model_name': self.lda_name,
							'raw_topic': topic,
							'topic_num': topic_num,
					}
					bulk.append(m_models.LDATopic(**params))
				m_models.LDATopic.objects.bulk_create(bulk)
			else:
				msg = 'LDA model with name={} already exists. Could not '
				msg += 'save topics to db.'
				logger.info(msg.format(self.lda_name))
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)

	def _get_topics_set(self):
		params = {'lda_model_name': self.lda_name}
		topics_set = m_models.LDATopic.objects.filter(**params)
		topics_set.update(optimized=True)

		# delete all trial runs
		params = {
				'domain__domain':self.domain,
				'domain__subdomain':self.subdomain,
				'optimized': False,
		}
		m_models.LDATopic.objects.filter(**params).delete()
		msg = 'Deleted LDATopic trial runs for params={}'.format(params)
		logger.info(msg)
		return topics_set

	def update_db_topics(self):
		'''
		Re-upload a csv of LDA topics with updated columns for lable, coherence,
		query, etc. 
		'''
		df = pd.DataFrame()
		try:
			df = pd.read_csv(self.path_topics)
		except IOError:
			msg = 'Pandas could not locate file={}'
			logger.exception(msg.format(self.path_topics))
		if not df.empty:
			topics_set = self._get_topics_set()
			for row in df.iterrows():
				content_dict = dict(row[1])
				topic_num = content_dict.get('topic_num')
				try:
					content_dict.pop('domain')
					topics_set.filter(topic_num=topic_num).update(**content_dict)
					msg = 'LDATopic updated. New row={}'.format(content_dict)
					logger.info(msg)
				except Exception as e:
					msg = '{}: {}'.format(type(e).__name__, e.args[0])
					logger.exception(msg)
		else:
			msg = 'DataFrame not found for file={}'.format(self.path_topics)
			logger.debug(msg)
			logger.info('Are you sure the file is in its proper directory?\n')

	def topics_to_csv(self):
		'''
		Output topics to a text file in a user-friendly format.
		'''
		params = {
				'lda_model_name': self.lda_name
		}
		topic_set = m_models.LDATopic.objects.filter(**params).order_by('topic_num')
		if topic_set.count():
			fields = ['domain', 'topic_num', 'coherent',
					 'raw_topic', 'query', 'label',]
			with open(self.path_topics, 'w') as csv_out:
				writer = csv.DictWriter(csv_out, fieldnames=fields)
				writer.writeheader()
				for topic_obj in topic_set:
					row_dict = {
							'domain': topic_obj.domain,
							'topic_num': topic_obj.topic_num,
							'coherent': topic_obj.coherent,
							'raw_topic': topic_obj.raw_topic,
							'query': topic_obj.query,
							'label': topic_obj.label,
					}
					writer.writerow(row_dict)
			logger.info('LDA topics saved to {}\n'.format(self.path_topics))
		else:
			msg = 'Could not find any topics in LDATopic table for {}\n'
			logger.info(msg.format(self.lda_name))

	def _tokenize(self, bow_docs):
		'''
		Tokenize each doc in bow_docs to be used in term first-inverse
		document frequency (Tf-df) calculation.
		'''
		nested_tokens = [[word for word in doc.lower().split()] for doc in bow_docs]
		return nested_tokens

	def _get_lda_bow(self, training=False, prediction=False):
		msg = 'Getting LDA BoW for {}...'
		if training:
			msg = msg.format('training')
		elif prediction:
			msg = msg.format('prediction')
		msg = msg.format(training, prediction)
		logger.info(msg)

		bow_set = self._get_bow_set()
		bow_docs = [obj.bow for obj in bow_set]
		for i in range(100):
			random.shuffle(bow_docs)
		nested_tokens = self._tokenize(bow_docs)
		id2word_dict = gensim.corpora.Dictionary(nested_tokens)
		if prediction:
			corpus_bow = [id2word_dict.doc2bow(doc_bow) for doc_bow in nested_tokens]
			return corpus_bow
		elif training:
			params = {
			'no_below': float(self.num_below),
			 'no_above': float(self.num_above), 
			 'keep_n': self.keep_n,
			}
			id2word_dict.filter_extremes(**params)
			corpus_bow = [id2word_dict.doc2bow(token) for token in nested_tokens]
			return id2word_dict, corpus_bow

	def _model_lda(self):
		id2word_dict, corpus_bow = self._get_lda_bow(training=True)
		params = {
				'corpus': corpus_bow,
				'id2word': id2word_dict,
				'num_topics': self.TOPIC_COUNT,
				'passes': self.passes,
				'chunksize': self.chunksize, 
		}
		lda = gensim.models.LdaMulticore(**params)
		self._save_trained_model(lda)
		return lda