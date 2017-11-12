import parsers.models as p_models
import ml.models as m_models
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class BaseNLP(object):
	def __init__(self, **kwargs):
		self.logger = logger
		# p_models = p_models
		self.m_models = m_models
		self.frsku = kwargs.get('frsku')
		self.domain = kwargs.get('domain')
		self.subdomain = kwargs.get('subdomain')
		self.training = kwargs.get('training')

	def get_review_set(self, **kwargs):
		review_mapper = kwargs.get('review_mapper')
		dedupe = kwargs.get('dedupe')
		nlp = kwargs.get('nlp')
		msg = 'Failed to evaluate conditional statements in get_review_set()'
		review_set = None
		if review_mapper:
			if self.training:
				params = {
					'ml_mapped': False,
					'domain': self.domain,
					'subdomain': self.subdomain,
					'is_training_data': True,
				}
				review_set = p_models.ReviewRaw.objects.filter(**params)
				msg = 'Retrieved TRAINING reviews for mapping'
			elif self.frsku:
				params = {
					'ml_mapped': False,
					'crawl_cache__crawl_queue__product_raw__product__frsku': self.frsku,
					'is_training_data': False,
				}
				review_set = p_models.ReviewRaw.objects.filter(**params)
				msg = 'Retrieved ANALYSIS reviews for mapping. FRSKU={}'
				msg = msg.format(self.frsku)

		elif dedupe:
			if self.training:
				params = {
					'unique': False,
					'trained': False,
					'review_raw__domain': self.domain,
					'review_raw__subdomain': self.subdomain,
				}
				review_set = self.m_models.TrainingCorpus.objects.filter(**params)
				msg = 'Retrieved review objects from TrainingCorpus for deduplication'
			elif self.frsku:
				params = {
				'unique': False,
				'analyzed': False,
				'review_raw__crawl_cache__crawl_queue__product_raw__product__frsku': self.frsku,
				}
				review_set = self.m_models.AnalysisCorpus.objects.filter(**params)
				msg = 'Retrieved review objects from AnalysisCorpus for ' 
				msg += 'deduplication. FRSKU={}'.format(self.frsku)

		elif nlp:
			if self.training:
				params = {
					'unique': True,
					'trained': False,
					'bow_parsed': False,
					'review_raw__domain': self.domain,
					'review_raw__subdomain': self.subdomain,
				}
				review_set = self.m_models.TrainingCorpus.objects.filter(**params)
				msg = 'Retrieved review objects from TrainingCorpus for NLP ' 
				msg += 'preprocessing.'
			elif self.frsku:
				params = {
				# 'unique': True,
				# 'analyzed': False,
				# 'bow_parsed': False,
				'review_raw__crawl_cache__crawl_queue__product_raw__product__frsku': self.frsku,
				}
				review_set = self.m_models.AnalysisCorpus.objects.filter(**params)
				msg = 'Retrieved review objects from AnalysisCorpus for NLP ' 
				msg += 'preprocessing. FRSKU={}'.format(self.frsku)

		if review_set.count():
			self.logger.info(msg)
		return review_set