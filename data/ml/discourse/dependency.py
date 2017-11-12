# import ml.machine_learning.prediction.sent_prediction as sp
import ml.models as m_models
from spacy.symbols import nsubj
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

# minimum sentence length (in word count)
# variable global because it's used in MetadataGenerator
# MIN_LENGTH = 5

class ShallowDependency(object):
	'''
	Performs shallow sentence discourse analysis using spaCy's dependency
	parser. 

	spaCy's dependency parser is capable of generating the complete 
	disourse structure of a sentence but we'll only be looking at 
	noun-verb relations.   

	Employing NLP preprocessing can significantly improve docvec sentence
	prediction.
	'''
	def __init__(self, **kwargs):
		self.frsku = kwargs.get('frsku')
		self.sent_set = self._get_documents()

	def _initialize_nlp(self):
		'''
		Load spaCy NLP module and process documents.

		Loading these modules takes a while so we only want to load
		them if we really need them.
		'''
		import spacy
		self.nlp = spacy.load('en_core_web_md')

	def _get_documents(self, d2v_training=False):
		'''
		Return a document set.
		'''
		doc_set = None
		key = 'review__review_raw__crawl_cache__crawl_queue'
		key += '__product_raw__product__frsku'
		params = {
			key : self.frsku,
		}
		if d2v_training:
			params['nlp_pass'] = True
		doc_set = m_models.SentenceTable.objects.filter(**params).\
					distinct('sentence')
		return doc_set

	def dependency(self):
		'''
		Look at the dependency tree of a sentence and make sure that 
		it has a noun subject and a root verb. If not, fail the sentence.

		What we are failing:
			1. Sentences with three words or fewer
			2. Sentences with fewer than two nouns
			3. Sentences that have the minimum number of words and nouns
				but lack grammatical structure
					- this is usually the case when we're dealing with 
					incomplete sentences, product descriptions, etc.

		We are failing any review that's short on substance.
		E.g. of a failed review:
			Really great value.  Feels like a pricing mistake.
			Great build quality, nice screen, quiet, 10-key with
			full size keyboard, big HDD, etc.

		Essentially, we're looking for reviews that do more showing
		than telling. We need verbs to capture emotions and actions
		while at the same time eliminating phrases that simply 
		enumerate product features. It's a bit harsh (one can argue
		that the above example does provde some useful information),
		but we want some quality reviews. 
		'''
		MIN_LENGTH = 5
		msg = 'Initiating dependency parsing for FRSKU={}'
		msg = msg.format(self.frsku)
		logger.info(msg)
		for sent_obj in self.sent_set:
			NOUN_SUBJECT = False
			VERB = False
			# set nlp_pass to True any sentence that has a verb and a noun
			# and whose parent review has at least MIN_LENGTH of words 
			word_count = sent_obj.review.word_count
			if word_count >= MIN_LENGTH:
				doc = self.nlp(sent_obj.sentence)
				for token in doc:
					if token.pos_ in ['NOUN', 'PRON', 'PROPN']:
						NOUN_SUBJECT = True
					if token.pos_ == 'VERB':
						VERB = True
				if all([NOUN_SUBJECT, VERB]):
					sent_obj.nlp_pass = True
					sent_obj.save()
		msg = 'Finished dependency parsing for FRSKU={}'.format(self.frsku)
		logger.info(msg)