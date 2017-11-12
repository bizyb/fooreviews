import parsers.analysis.review.review_parser as rparser
import parsers.analysis.detail.detail_parser as dparser
import crawler.queue.queuer as queuer
import crawler.analysis.detail.detail_crawler as detail_crawler
import crawler.analysis.review.review_crawler as review_crawler
import ml.discourse.aspect_rating as arat
import ml.discourse.summarizer as summ
import ml.meta.data_generator as dgen
import ml.nlp.preprocessor as preprocessor
import ml.machine_learning.modeling.topic_modeling as topic_modeling
import ml.machine_learning.modeling.document2vector as d2v
import ml.machine_learning.prediction.sent_prediction as spred
import ml.machine_learning.prediction.topic_prediction as tpred
import fooreviews.models as f_models
import ml.models as m_models
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class AnalysisWorkflow(object):
	# TODO: update the comments
	'''
	Controls the general workflow of crawling, parsing, and analysis.

	One of Workflow's main functions is to update the status fields of 
	ProductRaw and Product instances. We deal with network-related tasks
	and computationally intensive (not to mention time-consuming) 
	processes here. Because of the potential problems of frustratingly high 
	levels of duplication and proxy holdup, we have put in place multiple 
	redundant checks to prevent any step from being run more than once. 
	Workflow implements this when it retrieves the initial ProductRaw data 
	and when it calls the corresponding classes to process the information.
	Additionally, each of the staging functions (aren't always called staging)
	in the corresponding classes does its own status check. If we ever need 
	to redo any of the steps, the status field will have to be changed manually
	front the front-end. These would be exceptional cases where we have 
	encountered a new HTML structure.

	Crawling is dependent on a lot of variables that we have no control over.
	This mean that we cannot streamline the work with a single function call. 
	Parsing is also problematic because we'd still be dealing with external 
	data, where failures would have to be addressed appropriately. 

	Once we're satisfied with the crawling and parsing results, we can 
	streamline the remaining work. A single call to Workflow with 
	review_analysis=True should get us all the way to summarization and data 
	generation. The remaining task would be one we have to do manually like
	editing the summaries.

	Timing:
		1. Crawling can take anywhere from a few hours to a few days.
		2. Parsing should not take more than one or two hours 
			(this is based on parsing 0.4M training reviews). 
		3. NLP preprocessing could take at most 20-30 minutes
		4. ML modeling takes about 4 hours for LDA training corpus 
			(LDA could take up to several days, depending on 
				number of iterations and topic count we're trying 
				to optimize for. This is usually the case when we're 
				training a model for a new product domain). 
			Topic prediction and regression modeling takes about 30 
				minutes for a 1000-review product (prediction iteration 
					time scales linearly with 1 iteration = 1.5 seconds; 
					we do about 1000 iterations)
			Doc2vec models are trained on a product review corpus so 
				no domain training required. It usually takes about 5 
				minutes with our optimtized iteration count of 20. 
			Sentence prediction and db population takes about 10 minutes 
				for 50 features. Could take a lot longer with more features.
			Summarization and data generation:
				Takes 5-15 minutes.
		5. Draft editing and publication 
			Should not exceed 3 hours.

		Verdict:
			As it stands now, it takes 3-6 hours to generate a single article
			after crawling (the time of which is highly variable). We can 
			optimize this in the future to such an extent that the only 
			bottleneck is the machine learning step.
	'''
	def __init__(self, **kwargs):
		self.frsku = kwargs.get('frsku')
		self.corpus_training = kwargs.get('training')
		self.domain = kwargs.get('domain')
		self.subdomain = kwargs.get('subdomain')
		self.ignore_params = kwargs.get('ignore_params')
		self.recrawl_status = kwargs.get('recrawl')
		self.finished_crawling = kwargs.get('finished_crawling')
		self.finished_parsing = kwargs.get('finished_parsing')
		self.run_nlp = kwargs.get('run_nlp')
		self.run_ml = kwargs.get('run_ml')
		self.update_topics = kwargs.get('update_topics')
		self.domain = kwargs.get('domain')
		self.subdomain = kwargs.get('subdomain')
		self.clear_db = kwargs.get('clear_db')
		self.dump_to_csv = kwargs.get('dump_to_csv')
		self.parent = self._get_parent()
		self.merchant_list = self._get_merchants()
		self.raw_count = 0
		self.processed_count = 0
		self.debug = kwargs.get('debug')
		self.MSG = 'Set clear_db=True and reinitialize Workflow'

	def _get_parent(self):
		raw_product = f_models.ProductRaw.objects.filter(product__frsku=self.frsku)
		if raw_product:
			parent = raw_product[0].product
			return parent 
		return None

	def _get_merchants(self):
		params = {}
		if self.corpus_training:
			params = {
					'crawl': True,
			}
		merch_set = f_models.Merchant.objects.filter(**params).distinct('name')
		merchant_list = [m.name for m in merch_set] #if m.name != 'Walmart']
		return merchant_list

	def _get_params(self, task_code, processed=False):
		'''
		Return ProductRaw filtering parameters.

		Codes:
	        DC = Detail crawling
	        DP = Detail parsing
	        RQ = Review URL queuing
	        RC = Review URL crawling 
	        RP = Review parsing
	        ML = Machine learning 
	        # AP = Article publication # we might not need Workflow for this
		'''
		params = {
				'detail_crawled': False,
				'detail_parsed': False,
				'review_urls_queued': False,
				'review_urls_crawled': False,
				'reviews_parsed': False,
			}
		if task_code == 'DC':
			pass
		elif task_code == 'DP':
			params['detail_crawled'] = True
		elif task_code == 'RQ':
			params['detail_crawled'] = True
			params['detail_parsed'] = True
		elif task_code == 'RC':
			params['detail_crawled'] = True
			params['detail_parsed'] = True
			params['review_urls_queued'] = True
		elif task_code == 'RP':
			params['detail_crawled'] = True
			params['detail_parsed'] = True
			params['review_urls_queued'] = True
			params['review_urls_crawled'] = True
		elif task_code == 'ML':
			params['detail_crawled'] = True
			params['detail_parsed'] = True
			params['review_urls_queued'] = True
			params['review_urls_crawled'] = True
			params['reviews_parsed'] = True
		elif task_code == 'AP':
			params['detail_crawled'] = True
			params['detail_parsed'] = True
			params['review_urls_queued'] = True
			params['review_urls_crawled'] = True
			params['reviews_parsed'] = True
		return params
	
	def _get_product_set(self, task_code, processed=False):
		'''
		Return a set of ProductRaw instances for a given task code.
		'''
		params = self._get_params(task_code, processed=processed)
		# ignore filtering parameters when debugging
		if self.ignore_params:
			params = {'product__frsku': self.frsku}
		else:
			params['product__frsku'] = self.frsku

		product_set = f_models.ProductRaw.objects.filter(**params)
		if product_set.exists():
			if processed: 
				self.processed_count = product_set.count()
				return
			else:
				self.raw_count = product_set.count()
		msg = 'Retrieved {} ProductRaw instances for task={} FRSKU={}'
		logger.info(msg.format(product_set.count(), task_code, self.frsku))
		return product_set

	def _update_status(self, code, merchant=None):
		'''
		Update models.Product's task status accordingly based on 
		the status of all its children.

		NB: models.Product is the main product; models.ProductRaw
			is the merchant-specific instance of the product.

		Note that we are dealing with both current and future task 
		codes. Querying for the future task gives us the current 
		status.

		Updating the status for review_urls_crawled is somewhat non-trivial.
		Review crawling can fail for lots of reasons. As such, this requires 
		that we look at analysis_crawler.log carefully after every crawl and 
		decide whether we want to recrawl the failed URLs. Once we're satisfied
		with the results, we'll need to reinstantiate Workflow with
		finished_crawling=True
		'''
		if self.parent:
			fields = {
				'DP': 'detail_crawled',
				'RQ': 'detail_parsed',
				'RC': 'review_urls_queued',
				'RP': 'review_urls_crawled',
				'ML': 'reviews_parsed',
				'AP': 'reviews_analyzed',
				'APP': 'article_published',
			}
			attr = fields.get(code)
			if self.finished_crawling and code == 'RP':
				# update all ProductRaw instances whose parent has self.frsku
				pp = self.parent.product_raw_product.all()
				pp.update(review_urls_crawled=True)
				self.parent.review_urls_crawled = True
			elif code == 'ML':
				if merchant:
					# update the individual ProductRaw instance
					# reviews_analyzed only applies to
					# the parent Product object
					params = {
							'product__frsku': self.frsku,
							'merchant__name': merchant,
					}
					pr = f_models.ProductRaw.objects.filter(**params)
					pr.update(reviews_parsed=True)
				else:
					# update the parent Product instance; this means all 
					# ProductRaw instances for Prorduct have been updated
					self.parent.reviews_parsed = True
			else:
				self._get_product_set(task_code=code, processed=True)
				if self.raw_count == self.processed_count:
					setattr(self.parent, attr, True)
				else:
					setattr(self.parent, attr, False)
			self.parent.save()
			msg = 'Updated status={} for parent product with FRSKU={}'
			logger.info(msg.format(attr, self.frsku))

	def crawl_detail(self):
		product_set = self._get_product_set('DC')
		for raw_product in product_set:
			dc = detail_crawler.DetailCrawler(raw_product)
			dc.staging()
		self._update_status('DP')

	def parse_detail(self):
		product_set = self._get_product_set(task_code='DP')
		for raw_product in product_set:
			params = {
				'instance': raw_product,
				 'merchant': raw_product.merchant.name,
			}
			dp = dparser.DetailParser(**params)
			dp.parse()
		self._update_status('RQ')

	def queue_review_urls(self):
		product_set = self._get_product_set(task_code='RQ')
		for raw_product in product_set:
			params = {
				'prod_raw_instance': raw_product,
				'merchant': raw_product.merchant.name,
				'debug': self.debug,
			}
			q = queuer.CrawlQueuer(**params)
			q.queue()
		self._update_status('RC')

	def crawl_reviews(self):
		'''
		recrawl_status is externally issued after looking at the log file and 
		we decide to recrawl again, especially if the errors are network-related.

		possible recrawl_status: 'UNCRAWLED', 'FAILED'
		'''

		# set self.parent
		self._get_product_set(task_code='RC')
		if self.finished_crawling:
			self._update_status('RP')
		else:
			params = {
				'frsku': self.frsku,
				 'recrawl': self.recrawl_status,
				'debug': self.debug,
			}
			rc = review_crawler.ReviewCrawler(**params)
			rc.async_staging()
		
	def parse_reviews(self):
		'''
		Parse reviews found in CrawlCache for frsku or training corpus. 
		'''
		for merchant in self.merchant_list:
			kwargs = {
				'frsku': self.frsku,
				'merchant': merchant,
				'training': self.corpus_training,
				'domain': self.domain,
				'subdomain': self.subdomain,
				'debug': self.debug,
			} 
			rp = rparser.ReviewParser(**kwargs)
			count = rp.cache_set.count()
			if count:
				msg = 'About to parse {} pages for merchant={}'
				logger.info(msg.format(count, merchant))
				rp.parse()
			else:
				msg = 'No cache found for review parsing for merchant={} '
				if self.frsku:
					msg += 'FRSKU={}'
					msg = msg.format(merchant, self.frsku)
				elif self.domain:
					msg += 'domain={} subdomain={}'
					msg = msg.format(merchant, self.domain, self.subdomain)
				logger.info(msg)
				self._update_status('ML', merchant=merchant)


	def _nlp_workflow(self, params):
		'''
		Initiate review preprocessing and run nlp on the raw data. 
		'''
		msg = 'Workflow staging review mapping to {} for '
		if self.frsku:
			msg += 'FRSKU={}'
			msg = msg.format('AnalysisCorpus', self.frsku)
		elif self.corpus_training:
			msg += 'domain={} subdomain={}'
			msg = msg.format('TrainingCorpus', self.domain, self.subdomain)
		logger.info(msg)
		self._map_reviews(params)
		logger.info('Workflow finished review mapping')
		logger.info('Workflow staging review deduplication')
		self._deduplicate_reviews(params)
		logger.info('Workflow finished review deduplication')
		logger.info('Workflow staging nlp preprocessing')
		self._basic_nlp(params)
		logger.info('Workflow finished nlp preprocessing')

	def _ml_workflow(self, params):
		'''
		Initiate LDA, topic prediction, and document vectorization.
		'''
		if self.corpus_training:
			self._train_lda(params)
		elif self.frsku:
			logger.info('Workflow staging topic prediction')
			self._predict_topics()
			logger.info('Workflow finished topic prediction')
			logger.info('Workflow staging doc2vec model training')
			self._train_doc2vec()
			logger.info('Workflow finished doc2vec model training/loading')
			logger.info('Workflow staging sentence prediction')
			self._predict_sents()
			logger.info('Workflow finished sentence prediction')
			logger.info('Workflow staging aspect rating calculation')
			self._aspec_rating()
			logger.info('Workflow finished aspect rating calculation')
			logger.info('Workflow staging summarization')
			self._summarize()
			logger.info('Workflow finished summarization')
					
	def analyze_reviews(self):
		'''
		Perform review analysis.

		The analysis part uses review data that have already been standardized
		to our liking so there's no need to perform any merchant-specific 
		preprocessing. The only exception is the status update, where we have
		to update the children when we're updating the parent product. This 
		will be true for all nlp- and machine learning-related tasks.  
		'''
		params = {
				'domain': self.domain,
				'subdomain': self.subdomain,
				'training': self.corpus_training,
			}
		try:
			if self.run_nlp:
				self._nlp_workflow(params)
			elif self.run_ml or self.update_topics:
				self._ml_workflow(params)
			if self.frsku:
				# update Product/ProductRaw status flags; applies to frsku only
				for merchant in self.merchant_list:  
					self._update_status('ML', merchant=merchant)
				self._update_status('ML')
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)

	def _map_reviews(self, params):
		'''
		Establish Foreignkey relations betweeen review objects and ML tables
		without transferring any real data between the tables.
		'''
		if self.corpus_training:
			cdm = preprocessor.CorpusDataMapper(**params)
		elif self.frsku:
			cdm = preprocessor.CorpusDataMapper(frsku=self.frsku)
		if cdm.raw_set.count():
			cdm.mapper()
		else:
			if self.corpus_training:
				msg = 'Could not find any reviews for mapping for '
				msg += 'domain={} subdomain={}'
				msg = msg.format(self.domain, self.subdomain)
			elif self.frsku:
				msg = 'Could not find any reviews for mapping with FRSKU={}'
				msg = msg.format(self.frsku)
			logger.info(msg)

	def _deduplicate_reviews(self, params):
		'''
		Initiate review deduplication. 
		'''
		msg = 'Deduplication initiated for review '
		if self.corpus_training:
			dd = preprocessor.Deduplicate(**params)
			msg += 'training. Domain={} Subdomain={}'
			msg = msg.format(self.domain, self.subdomain)
		elif self.frsku:
			dd = preprocessor.Deduplicate(frsku=self.frsku)
			msg += 'analysis. FRSKU={}'.format(self.frsku)
		dd.dedupe()
		logger.info(msg)
	
	def _basic_nlp(self, params):
		'''
		Initiate basic NLP preprocessing for generating a bag of words 
		corpus used in the machine learning step for modeling (in training)
		or for topic prediciton and vector inference (in analysis).
		This step also populates the db with bow_count, word_count, 
		and sentence_count, which will be used later in classification
		and metadata generation.
		'''
		while True:
			if self.corpus_training:
				nlpp = preprocessor.NLPreprocessor(**params)
			elif self.frsku:
				nlpp = preprocessor.NLPreprocessor(frsku=self.frsku) 
			if nlpp.review_set.count() > 0:
				nlpp.parse_BoW()
				msg = 'Parsed bag of words for '
				if self.corpus_training:
					msg += 'Domain={} Subdomain={}'
					msg = msg.format(self.domain, self.subdomain)
					logger.info(msg)
				elif self.frsku:
					msg += 'FRSKU={}'.format(self.frsku)
					logger.info(msg)
			else:
				msg = 'Workflow could not find any reviews to '
				msg += 'initiate bag of words parsing'
				logger.info(msg)
			break

	def _train_lda(self, params):
		tm = topic_modeling.TopicModeling(**params)
		lda = tm.train_lda_model()
		if not lda:
			lda = tm.train_lda_model(new_model=True)
		if self.update_topics:
			tm.update_db_topics()
		elif lda and not self.update_topics:
			tm.topics_to_csv()
		
	def _predict_topics(self):
		'''
		Initiate LDA topic prediction.
		'''
		tp = tpred.TopicPrediction(frsku=self.frsku, clear_db=self.clear_db)
		tp.stage_prediction()
		if self.dump_to_csv:
			# for debugging
			tp.predictions_to_csv() 

	def _train_doc2vec(self):
		'''
		Initiate a new doc2vec model training for FRSKU.
		'''
		d = d2v.Document2Vector(frsku=self.frsku)
		d.train_d2v_model(new_model=True)
		
	def _predict_sents(self):
		'''
		Initiate doc2vec sentence prediction for FRSKU. Output the results 
		for analysis and validation.
		'''
		sp = spred.SentencePrediction(frsku=self.frsku, clear_db=self.clear_db)
		sp.predict()
		sp.predictions_to_file()
		sp.get_validation_files()

	def _aspec_rating(self):
		'''
		Initiate product aspect rating calculation.
		'''
		ar = arat.AspectRating(frsku=self.frsku, clear_db=self.clear_db)
		ar.aspect_rating()

	def _summarize(self):
		'''
		Initiate sentence summarization.
		'''
		s = summ.Summarize(frsku=self.frsku, clear_db=self.clear_db)
		s.summarize()

	def generate_data(self):
		'''
		NB: data generator must be run after manually selecting analysis
		components. Otherwise, Topic Distribution All will be set to 100% Other
		instead of the top ten and bottom ten topics that should be grouped in 
		this category distribution. The other group, Topic Distribution Summ, 
		includes all the distributions, whether they're analysis component or
		not. This is the only pre-condition for data generation. 
		'''
		d = dgen.MetadataGenerator(frsku=self.frsku, clear_db=True)
		d.generate_data()

	def summary_to_file(self):
		'''
		Output summarized data to file.

		NB: This step must be executed after selecting analysis components. 
		Otherwise, no topical summaries will be outputted for the topical_anl 
		group.
		'''
		s = summ.Summarize(frsku=self.frsku)
		s.summary_to_file()

	def async_staging(self, task):
		task_funcs = {
			'crawl_detail': self.crawl_detail,
			'parse_detail': self.parse_detail,
			'queue_review_urls': self.queue_review_urls,
			'crawl_reviews': self.crawl_reviews,
			'parse_reviews': self.parse_reviews,
			'analyze_reviews': self.analyze_reviews,
			'generate_data': self.generate_data,
			'summary_to_file': self.summary_to_file,
		}
		func = task_funcs.get(task)
		try:
			func()
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)