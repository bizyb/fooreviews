
import ml.models as m_models
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()
class Classify(object):
	'''
	Performs review classification. Reviews are classified into 
	positive or negative sentiment groups, spam, ham, duplicate, etc.
	'''

	def __init__(self, frsku, **kwargs):
		self.frsku = frsku
		self.corpus = self._get_analysis_corpus()

	def _get_analysis_corpus(self):
		params = {
			'review_raw__crawl_cache__crawl_queue__product_raw__product__frsku': self.frsku, 
		}
		review_set = m_models.AnalysisCorpus.objects.filter(**params)
		return review_set
	def sent_group(self):
		'''
		Classify reviews based on their star rating. 
			Positive sentiment: 	rating
									4.0, 5.0
			Negative sentiment 		3.0, 2.0, 1.0

			NB: We're dealing with individual reviews so it's not possible to 
			have a non-whole number rating. 

		'''
		self.corpus.update(pos_sent_group=False)
		self.corpus.filter(review_raw__rating=5.0).update(pos_sent_group=True, neg_sent_group=False)
		self.corpus.filter(review_raw__rating=4.0).update(pos_sent_group=True, neg_sent_group=False)
		self.corpus.filter(pos_sent_group=False).update(neg_sent_group=True)

	def spam_ham(self):
		'''
		Classify reviews as spam or ham (legitimate and content-rich) based on 
		the meta data collected during various stages of ml.
		'''
		pass