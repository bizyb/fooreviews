import collections
import csv
import ml.machine_learning.modeling.document2vector as d2v
import ml.models as m_models
import random
import services.common_helper as ch
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class SentencePrediction(d2v.Document2Vector):
	'''
	Performs sentence prediction using predicted LDA topics.
	'''

	def __init__(self, **kwargs):
		super(SentencePrediction, self).__init__(**kwargs)
		self.clear_db = kwargs.get('clear_db')
		self.topic_set = self._get_topics()
		self.train_d2v_model(new_model=False)
		self.topn = 100
		if self.clear_db:
			m_models.PredictedSent.objects.filter(frsku=self.frsku).delete()

	def _get_topics(self):
		params = {
				'product__frsku': self.frsku,
		}
		topic_set = m_models.PredictedLDATopic.objects.filter(**params)
		topic_set = topic_set.order_by('rank')
		return topic_set

	def predict(self):
		'''
		Get predicted sentences and format them for outputting.
		'''
		EXISTS = m_models.PredictedSent.objects.filter(frsku=self.frsku).exists()
		if not EXISTS:
			msg = 'Initiating sentence prediction for FRSKU={}...'
			msg = msg.format(self.frsku)
			logger.info(msg)
			predictions = collections.OrderedDict()
			for topic_obj in self.topic_set:
				raw_topic = topic_obj.topic.raw_topic
				query = topic_obj.topic.query.lower()
				pred_sents = self.infer_vectors(topic=query, topn=self.topn)
				predictions[topic_obj.rank] = pred_sents
			msg = 'Finished sentence prediction for FRSKU={}\n'
			msg = msg.format(self.frsku)
			logger.info(msg)
			# self._predictions_to_db(predictions)
		else:
			msg = 'Sentences have already been predicted for frsku={}. '
			msg += 'Aborting process...\n'
			logger.info(msg.format(self.frsku))

	def _predictions_to_db(self, predictions):
		'''
		Save predicted sentences to db.

		NB: We can't selectively remove a predicted sentence; we have to clear 
			the table for a given frsku if we want to re-run the predction. 
			Re-running the prediction is not deterministc (doc2vec documentation
			suggests randomized seed value; this can be changed but it's better
			to keep it random).
		'''
		msg = 'Initiating sentence addition to db for FRSKU={}...'
		msg = msg.format(self.frsku)
		logger.info(msg)
		for topic_rank, pred_sents in predictions.items():
				label = self.topic_set.filter(rank=topic_rank)[0].topic.label
				z = self._reverse_sent(pred_sents)
				for index, zipped in enumerate(z):
					raw_sent = zipped[2].encode('utf-8')
					row_dict = {
						'topic_rank': topic_rank,
						'label': label,
						'raw_sent_rank': index + 1,
						'sent_valid': True, 
						'review_rating': zipped[3],
						'raw_sent': raw_sent,
						'tag_uuid': zipped[0],
						'frsku': self.frsku,
						'probability': zipped[1],
					}
					if row_dict.get('probability') >= 0.5:
						obj = m_models.PredictedSent.objects.create(**row_dict)
						msg = 'Saved new PredictedSent object. Sentence={} '
						msg += 'sent_pk={}'
						msg = msg.format(raw_sent, obj.id)
						logger.info(msg)
						pass # for debugging
		msg = 'Finished sentence addition to db for FRSKU={}...'
		msg = msg.format(self.frsku)
		logger.info(msg)

	def _reverse_sent(self, pred_sents):
		'''
		Do a reverse a sentence lookup using the uuid tag provided
		and return a dictionary with the sentence and other relevant
		fields.

		NB: map always returns an iterable;
			pred_sents is the raw prediction given by doc2vec. It's a 
			a list of two-element tuples where the index=0 is the uuid sentence 
			tag and index=1 is the probability, like so:
				[
				(u'21437f42-6684-4f2d-bd09-716663df8424', 0.3427872657775879), 
				(u'e998de9c-7fa2-470c-88bb-a2f503099884', 0.30058854818344116),
				...
				]
			A note on mapping lambda functions: the process is the same as 
			list comprehension. The only reason we use them here is because 
			it's less verbose. 

		Return object z has the following form, where each element encapsulates 
		all the attributes of a single sentence:
		z = [
				(u'2a6d5340-2017-4a0c-a4c1-a5ee526b632d', 0.6444320678710938,
				 u'Everyone loves them!', Decimal('5.0')),
				(u'6455a897-f2a2-4ce1-847d-38e75a908048', 0.6174625158309937,
				 u'Ice cream is practically melted.', Decimal('2.0')),
				.....
			]

		'''
		tags = map(lambda x: x[0], pred_sents)
		probs = map(lambda x: x[1], pred_sents)
		sents = map(lambda x: x[0].sentence, \
				(m_models.SentenceTable.objects.filter(tag=t) for t in tags))
		ratings = map(lambda x: x[0].review.review_raw.rating, \
				(m_models.SentenceTable.objects.filter(tag=t) for t in tags))
		z = zip(tags, probs, sents, ratings)
		return z

	def _get_unique_topics(self, sent_iterable):
		topic_list = [obj.topic_rank for obj in sent_iterable]
		return sorted(set(topic_list))

	def _sort_iterable(self, sent_iterable):
		topic_ranking = self._get_unique_topics(sent_iterable)
		new_iterable = []
		for rank in topic_ranking:
			sent_set = sent_iterable.filter(topic_rank=rank).\
						order_by('raw_sent_rank')
			new_iterable.extend([obj for obj in sent_set])
		return new_iterable

	def _sents_to_csv(self, sent_iterable, path, validation=False):
		'''
		Output predicted sentences to csv for analysis or validation.
		Incoming sentence objects have already been sorted by topic rank.
		Here we sort the sorted sentences by sentence rank so that the 
		csv is sorted by topic rank as a whole and each topic is internally
		ranked by its sentence ranks.
		'''
		fields = ['topic_rank', 'label', 'raw_sent', 'raw_sent_rank', 
					'review_rating', 'probability', 'tag_uuid', 'frsku',  
					'summary_component']
		if validation:
			fields.append('sent_valid')
		with open(path, 'w') as csv_out:
			writer = csv.DictWriter(csv_out, fieldnames=fields)
			writer.writeheader()
			if not validation:
				# we can't sort validation sentences; the iteratble is a list,
				# not a queryset
				sent_iterable = self._sort_iterable(sent_iterable)
			for sent_obj in sent_iterable:
				sent_dict = sent_obj.__dict__
				row_dict = {k: v for k, v in sent_dict.items() if k in fields}
				writer.writerow(row_dict)
		msg = 'Predicted sentences saved to {}\n'
		logger.info(msg.format(path))
		

	def predictions_to_file(self, validation=False):
		'''
		Output predicted sentences to csv for analysis.
		NB: Each topic has sentences ranked from 1 to self.topn.
		'''
		root = 'file_dump/doc2vec/analysis/'
		ch.make_directory(logger, root)
		filename = self.d2v_model_path.split('/')[-1].replace('MODEL', 'SENTS')
		filename = root + filename + '.csv'
		params = {
			'frsku': self.frsku,
		}
		sent_set = m_models.PredictedSent.objects.filter(**params)
		sent_set = sent_set.order_by('topic_rank')
		self._sents_to_csv(sent_set, filename)
		

	def get_validation_files(self, trials=5, samples=100):
		'''
		Output prediction results for validation. The default setting
		is 5 trials (5 files) and 100 rows per trial. 

		Validation requires manual inspection of the predicted sentences and
		verifying whether or not they're valid within a doc2vec prediction 
		context, not on whether or not the sentences fully conform ot the topic 
		they were queried for. What this means is that we're essentially 
		scoring how accurate the doc2vec algorithm is at doing at what's told, 
		not necessarily on whether we like the output. 
		E.g.
			query: shipping, delivery, transit, time
			prediction: I'm not a fan of how Apple products become absolute 
						in short order.  			 
			valid: True
			Reason: The prediction is not wrong because our query had 'time' in 
					it and the response has a variation of that term, 
					'short order', in it. Of course, this is an extreme case
					because although most people don't talk like that, it shows 
					that the algorithm can decipher conceptually related terms 
					even if there is no syntactic relation between them. 
			What this means: We need to be careful with our topic labeling. We 
							should pick keywords that are cohesive and less 
							likely to be used in a different context.

			Sometimes, the model can predict documents that are just outright.
			wrong. Other times, it can predict documents that are wrong but 
			only so because they're ambiguous. These ambiguities are most 
			likely due to data sparsity, which can be fixed. Fixing the other 
			issues and bringing the accuracy to within two standard deviations 
			would require more research, bigger data set, and making 
			idiosyncratic optimizations, i.e. domain-specific, at either query 
			construction or hyperparameter tuning stage. 

		The resulting True/False values are tallied to get 
		experiment-level accuracy as well as an overall mean accuracy. 
		Current observations on an experimental set of data (1042 reviews)
		give us a mean accuracy of 86%. It is conceivable that with improved 
		topic labeling and more review data per product, we can achieve a mean
		accuracy in the low- to mid-90s. 

		Since this entire learning process is unsupervised, the validation acts 
		as our first true means of gauging how good our optimizations
		are.   
		'''
		sent_set = m_models.PredictedSent.objects.filter(frsku=self.frsku)
		sent_list = [obj for obj in sent_set]
		fields = [field.name for field in sent_set[0]._meta.fields]
		ROW_COUNT = sent_set.count()
		for i in range(ROW_COUNT):
			random.shuffle(sent_list)
		for i in range(trials):
			try:
				root = 'file_dump/doc2vec/validation/'
				ch.make_directory(logger, root)
				filename = self.d2v_model_path.split('/')[-1]
				filename = filename.replace('MODEL', 'VALIDATION')
				filename = root + filename + '_T{}.csv'
				filename = filename.format(i+1)
				sent_iterable = []
				for j in range(samples):
					index = random.randint(0, ROW_COUNT-1)
					sent_iterable.append(sent_list[index])
				self._sents_to_csv(sent_iterable, filename, validation=True)
				msg = 'Wrote doc2vec validation file to'.format(filename)
				logger.info(msg)
			except Exception as e:
				msg = '{}: {}'.format(type(e).__name__, e.args[0])
				logger.exception(msg)