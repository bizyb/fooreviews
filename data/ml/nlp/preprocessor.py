from concurrent.futures import ThreadPoolExecutor
import copy
import fooreviews.models as f_models
import ml.nlp.__base__ as base_nlp
import parsers.models as p_models
import re
import spacy
from uuid import uuid4


class CorpusDataMapper(base_nlp.BaseNLP):
	'''
	Maps raw reviews found in ReviewRaw to either TrainingCorpus or 
	AnalysisCorpus through ForeignKey relations.
	'''

	def __init__(self, **kwargs):
		super(CorpusDataMapper, self).__init__(**kwargs)
		self.raw_set = super(CorpusDataMapper, self).\
						get_review_set(review_mapper=True)

	def _object_exists(self, obj):
		EXISTS = False
		params = {'review_raw__id': obj.id}
		if self.training:
			EXISTS= self.m_models.TrainingCorpus.objects.filter(**params).exists()
		elif self.frsku:
			EXISTS= self.m_models.AnalysisCorpus.objects.filter(**params).exists()
		return EXISTS

	def _get_overlap_set(self):
		'''
		Return analysis reviews from TrainingCorpus if available. 

		These would be reviews we already trained on. Sometimes a given FRSKU 
		might refer to a product that we already encountered before. In an ideal 
		world, we would rather avoid testing/analyzing reviews that are already 
		part of our training set. However, there are a finite number of products 
		out there for any given domain/subdomain combination that we can use 
		for trainig. When we decide to analyze a product, the overlap becomes 
		unavoidable because our training set pretty much took all the products 
		out there for any given merchant meeting our criteria. The only way this 
		conflict won't happen is if some time has elapsed since our training and 
		new products with a sufficient number of reviews have become available.
		'''
		overlap_obj_list = []
		field = 'crawl_cache__crawl_queue__crawl_corpus_parsed__product_id'
		prset = f_models.ProductRaw.objects.filter(product__frsku=self.frsku)
		merchant_id_list = [obj.source_product_id for obj in prset]
		for mer_id in merchant_id_list:
			params = {
				field: mer_id
			}
			overal_set = p_models.ReviewRaw.objects.filter(**params)
			overlap_obj_list.extend([obj for obj in overal_set])
		msg = 'Found {} ovelapping reviews'.format(len(overlap_obj_list))
		self.logger.info(msg)
		return overlap_obj_list, len(overlap_obj_list)

	def mapper(self):
		sorted_raw_set = self.raw_set.order_by('id')
		for index in range(len(sorted_raw_set)):
			obj = sorted_raw_set[index]
			if not self._object_exists(obj):
				if self.training:
					self.m_models.TrainingCorpus.objects.create(review_raw=obj)
				elif self.frsku:
					self.m_models.AnalysisCorpus.objects.create(review_raw=obj)
				msg = 'Mapped domain={} subdomain={}, review_pk={}'
				obj.ml_mapped = True
				obj.save()
			else:
				msg = 'Mapped object already exists. Domain={} subdomain={} '
				msg += 'review_pk={}'
			msg = msg.format(self.domain, self.subdomain, obj.id)
			self.logger.info(msg)
		if not len(sorted_raw_set):
			self.logger.info('No reviews have been mapped')
		if self.frsku:
			self._map_overlap()

	def _map_overlap(self):
		overlapping_set, count = self._get_overlap_set()
		if count:
			msg = 'About to map {} overlapping reviews for FRSKU={}'
			msg = msg.format(count, self.frsku)
			self.logger.info(msg)
			for obj in overlapping_set:
				if not self._object_exists(obj):
					self.m_models.AnalysisCorpus.objects.create(review_raw=obj)
					msg = 'Mapped domain={} subdomain={}. Overlap review_pk={}'
					msg = msg.format(self.domain, self.subdomain, obj.id)
				else:
					msg = 'Mapped object already exists. Overlap review_pk={}'
					msg = msg.format(obj.id)
				self.logger.info(msg)

class Deduplicate(base_nlp.BaseNLP):
	'''
	Removes duplicate reviews from a corpus. 
	'''

	def __init__(self, **kwargs):
		super(Deduplicate, self).__init__(**kwargs)
		self.THREAD_COUNT = 10
		
	def dedupe(self):
		'''
		Perform a shallow deduplication by removing reviews whose body matches
		exactly that of another review. 
		'''
		field = 'review_raw__review_body'
		model_sets = {
				'training': self.m_models.TrainingCorpus.objects,
				'analysis': self.m_models.AnalysisCorpus.objects,
		}
		# sets QuerySet to return a list instead of a tuple
		params = {'flat':True} 
		if self.training:
			model_set = model_sets.get('training')
		elif self.frsku:
			model_set = model_sets.get('analysis')

		# process the deduplication asynchronously
		# Can confirm the threading makes some noticeable improvement 
		review_set = super(Deduplicate, self).get_review_set(dedupe=True)
		if review_set.count() > 0:
			with ThreadPoolExecutor(max_workers=self.THREAD_COUNT) as executor:
				# original code from StackOverflow
				for body in model_set.values_list(field, **params).distinct():
					executor.submit(self._async, body, field, model_set)
			review_set.update(unique=True)
			if self.frsku:
				msg = 'Updated reviews to unique for AnalysisCorpus'
			elif self.training:
				msg = 'Updated reviews to unique for TrainingCorpus'
		else:
			msg = 'Could not find any reviews to deduplicate for '
			if self.frsku:
				msg += 'FRSKU={}'.format(self.frsku)
			elif self.training:
				msg += 'training. Domain={} Subdomain={}'
				msg = msg.format(self.domain, self.subdomain)
		self.logger.info(msg)


	def _async(self, body, field, model_set):
		# TODO: this looks at all the reviews in the db; could 
		# become slow of millions of reviews
		msg = 'New thread initiated for deduplication. '
		if self.training:
			msg += 'Corpus=True Domain={} Subdomain={}'
			msg = msg.format(self.domain, self.subdomain)
		elif self.frsku:
			msg += 'FRSKU={}'.format(self.frsku)
		self.logger.info(msg)
		model_set.filter(pk__in=model_set.filter(**{field:body}).\
								values_list('id', flat=True)[1:]).delete()

class NLPreprocessor(base_nlp.BaseNLP):
	'''
	Performs NLP analysis such as tokenization, lemmatization, stop word
	identification, etc. using the spaCy NLP framework. 
	'''

	def __init__(self, **kwargs):
		super(NLPreprocessor, self).__init__(**kwargs)
		self.review_set = super(NLPreprocessor, self).get_review_set(nlp=True)
		self.doc_list = self._get_docs()
		self.bow_str = ''

		# load the more comprehensive English model
		if len(self.doc_list):
			self.logger.info('Loading spaCy NLP model...')
			self.nlp = spacy.load('en_core_web_md')

	def _get_docs(self):
		docs = []
		if self.review_set.count():
			docs = [obj.review_raw.review_body for obj in self.review_set]
			# for debugging
			# docs = [self.review_set[0].review_raw.review_body] 
		return docs

	def _get_sentence(self, doc, sent_list=None, review_obj=None):
		AD = '[This review was collected as part of a promotion.]'
		if review_obj and sent_list:
			bulk = []
			for sentence in sent_list:
				if AD not in sentence:
					entry = {
						'review': review_obj,
						'sentence': sentence,
						'tag': str(uuid4()),
					}
					bulk.append(self.m_models.SentenceTable(**entry))
			if bulk:
				msg = 'Bulk SentenceTable object created for review_pk={}'
				msg = msg.format(review_obj.id)
				self.logger.info(msg)
			return bulk
		else:
			sent_list = []
			for sentence in doc.sents:
				s = sentence.text
				if s != AD:
					sent_list.append(s)
					self.logger.info('New Sentence: {}'.format(s)) 
			sent_count = len(sent_list)
			return sent_list, sent_count

	def _get_review(self, doc):
		review = ''
		word_count = 0
		if doc:
			review = doc.text
			word_count = len(review.split())
		return review, word_count

	def _review_reverse_lookup(self, review):
		'''
		Locate the review object a given sentence belongs to.

		NB: We have no way of keeping track of the reviews during spaCy's piped
		parsing step
		'''
		params = {
			'review_raw__review_body':review,
		}
		# expect a single match since all reviews are unique
		if self.frsku:
			found = self.m_models.AnalysisCorpus.objects.filter(**params)
		elif self.training:
			found = self.m_models.TrainingCorpus.objects.filter(**params)
		review_obj = found[0]
		return review_obj
		
	def _populate_sent_table(self, doc):
		'''
		Populate SentenceTable using the sentences found in doc.
		This process is only used in analysis, not training. SentenceTable is 
		used in document vectorization.

		NB: We're not saving the sentences to db just yet. parse_bow needs to 
		be verify that there are enough number of nouns and noun phrases in the 
		review as a whole before its sentence table can be populated.
		'''
		review_obj = -1
		bulk = []
		sent_count = 0
		sent_list, sent_count = self._get_sentence(doc)
		review, word_count = self._get_review(doc)			
		if doc and sent_list:
			try:
				review_obj = self._review_reverse_lookup(review)
				if self.frsku:
					# SentenceTable not needed for training
					bulk = self._get_sentence(doc,
										sent_list=sent_list,
										 review_obj=review_obj)
			except Exception:
				# we're mostly catching IndexError but we may also 
				# encounter others
				msg = 'Could not locate {} review for \'{}...\''
				if self.training:
					msg = msg.format('TrainingCorpus', sent_list[0])
				elif self.frsku:
					msg = msg.format('AnalysisCorpus', sent_list[0])
				self.logger.exception(msg)
		kwargs = {
			'review_obj': review_obj,
			'bulk': bulk,
			'sent_count': sent_count,
			'word_count': word_count,
		}
		return kwargs

	def _get_nouns(self, doc):
		nouns = []
		for np in doc.noun_chunks:
			for token in np:
				# ignore stop words and other non-nouns in the noun phrase
				lemma = token.lemma_
				if token.pos_ == 'NOUN' and len(lemma) > 1:
					# only add nouns longer than one letter
					# e.g. the 'c' in the noun phrase 'usb c' is dropped
					nouns.append(lemma)
		return nouns

	def _clean_bow(self, nouns):
		'''
		Return a single bag of words string after removing any non-alphanumeric
		characters.
		'''
		raw_bow = ' '.join(nouns)
		cleaned_tokens = re.findall(r'\w+', raw_bow)
		bow_str = ' '.join(cleaned_tokens)
		bow_count = len(cleaned_tokens) # later used in spam/ham classification
		return bow_str, bow_count

	def _no_bow(self, **kwargs):
		'''
		Update the status field of review objects lacking any bag of words.

		NB: Lack of bag of words is an indication of thin content review.
		'''
		try:
			review_obj = kwargs.get('review_obj')
			review_obj.bow_parsed = True 
			if self.frsku:
				word_count = kwargs.get('word_count')
				sent_count = kwargs.get('sent_count')
				review_obj.bow_count = 0
				review_obj.sentence_count = sent_count
				review_obj.word_count = word_count
			review_obj.save()
			msg = 'No bag of words found for {} review pk={}\n'
			if self.training:
				msg = msg.format('TrainingCorpus', review_obj.id)
			elif self.frsku:
				msg = msg.format('AnalysisCorpus', review_obj.id)
			self.logger.info(msg)
		except AttributeError:
			msg = 'Sorry, no valid review_obj found to update bow status\n'
			self.logger.info(msg)

	def _get_params(self, corpus, review_obj, bow_str):
		params = {
			'training':  {
						'a_review': None,
						't_review': review_obj,
						'bow': bow_str,
						'is_training_bow': True,
						'is_analysis_bow': False,

				},
			'analysis': {
						't_review': None,
						'a_review': review_obj,
						'bow': bow_str,
						'is_training_bow': False,
						'is_analysis_bow': True,
				},
			}
		return params.get(corpus)
	def _object_exists(self, review_obj):
		if self.training:
			params = {'t_review__id': review_obj.id}
		elif self.frsku:
			params = {'a_review__id': review_obj.id}
		EXISTS = self.m_models.BagofWords.objects.filter(**params).exists()
		return EXISTS

	def _save_BoW(self, **kwargs):
		'''
		Save the bag of words along with its proper domain/subdomain if for 
		training or frsku if for analysis.
		'''
		msg = 'Could not save BoW to db'
		review_obj = kwargs.get('review_obj')
		bow_str = kwargs.get('bow_str')
		bow_count = kwargs.get('bow_count')
		sent_count = kwargs.get('sent_count')
		word_count = kwargs.get('word_count')
		if not self._object_exists(review_obj):
			if self.training:
				params = self._get_params('training', review_obj, bow_str)
				bow_obj = self.m_models.BagofWords.objects.create(**params)
				msg = 'Saved BoW for TRAINING. Domain={} Subdomain={}'
				msg += 'BoW pk={}\n'
				msg = msg.format(self.domain, self.subdomain, bow_obj.id)
			elif self.frsku:
				params = self._get_params('analysis', review_obj, bow_str)
				bow_obj = self.m_models.BagofWords.objects.create(**params)
				review_obj.bow_count = bow_count
				review_obj.sentence_count = sent_count
				review_obj.word_count = word_count
				msg = 'Saved BoW for ANALYSIS. FRSKU={} BoW pk={}\n'
				msg = msg.format(self.frsku, -999) #bow_obj.id)
			review_obj.bow_parsed = True
			review_obj.save()
			self.logger.info(msg)
		else:
			msg = 'Bag of words already exists for {} pk={}\n'
			if self.training:
				msg = msg.format('TrainingCorpus', review_obj.id)
			elif self.frsku:
				msg = msg.format('AnalysisCorpus', review_obj.id)
			self.logger.info(msg)

	def _save_sentences(self, bulk):
		'''
		Inspect SentenceTable bulk object to make sure no table 
		entry exists for a given object and then create a new 
		entry.
		'''
		for index, obj in enumerate(bulk):
			# check to see if the sentence exists; NB; we cannot use the 
			# sentence tag even though it's unique because a unique one is 
			# generated every time we run the script; Instead, we use a 
			# deterministic pair of values that are guaranteed to be unique, 
			# independent of however many times we run the script. If the 
			# uniqueness fails, then the problem lies in our dependency parser
			lookup = {
				'sentence': obj.sentence,
				'review__id': obj.review.id,
			}
			if self.m_models.SentenceTable.objects.filter(**lookup).exists():
				msg = 'SentenceTable entry already exists for sentence={} '
				msg += 'review_pk={}'
				self.logger.info(msg.format(obj.sentence, obj.review.id))
				bulk.pop(index)
		if bulk:
			self.m_models.SentenceTable.objects.bulk_create(bulk)

	def parse_BoW(self):
		'''
		Return a bag of words consisting of nouns and noun phrases 
		for a corpus.

		spaCy's POS tagging is not perfect. Some obvious adjectives 
		and other non-nouns can still make it into the BOW. This is 
		mostly due to syntax issues, e.g.
			...excellent.Now...
		Both 'excellent' (verified) and probably 'now' (unverified)
		make it into the bow corpus. We should be mindful of these kinds 
		of errors because they can show up in the final trained model and 
		make it difficult to optimize the hyperparameters.  
		'''
		for doc in self.nlp.pipe(self.doc_list, n_threads=4, batch_size=100):
			try:
				kwargs =self._populate_sent_table(doc)
				doc_bow = ''
				nouns = self._get_nouns(doc)
				if nouns:
					bow_str, bow_count = self._clean_bow(nouns)
					self.logger.info('New BoW: {}'.format(bow_str))
					if self.frsku:
						self._save_sentences(kwargs.pop('bulk'))
					kwargs['bow_str'] = bow_str
					kwargs['bow_count'] = bow_count
					self._save_BoW(**kwargs)
				else:
					self._no_bow(**kwargs)
			except Exception as e:
				msg = '{}: {}'.format(type(e).__name__, e.args[0])
				self.logger.exception(msg)

