from collections import namedtuple
from datetime import timedelta
from gensim.models.doc2vec import Doc2Vec
import ml.discourse.dependency as dep
# import ml.models as m_models
import os
import random
from time import time
import services.common_helper as ch
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class Document2Vector(dep.ShallowDependency):
	'''
	Performs doc2vec modeling using gensim's doc2vec implementation.
	'''
	def __init__(self, **kwargs):
		super(Document2Vector, self).__init__(**kwargs)
		self.nlp = None
		self.d2v_model = None
		self.size = 100
		self.iterations = 20
		self.min_count = 20
		self.doc_list = []
		self.d2v_model_path = self._get_path()
		self.training_params = self._get_training_params()
	
	def _get_path(self):
		root = 'ml/trained_models/doc2vec/'
		filename = 'doc2vec_MODEL_{}_size{}_iter{}_min{}'
		filename = filename.format(self.frsku, self.size, self.iterations, \
									self.min_count)
		path = root + filename
		ch.make_directory(logger, root)
		return path

	def _get_training_params(self):
		'''
		Set doc2vec training parameters.

		Default arguments:
		Doc2Vec(documents=None, dm_mean=None, dm=1, dbow_words=0, dm_concat=0, 
				dm_tag_count=1, docvecs=None, docvecs_mapfile=None, 
				comment=None, trim_rule=None, **kwargs)
		
		dm: distributed memory (algorithm to use for training)
		size: dimensionality of the feature vectors
		negative: number of noise words to (down?) sample
		min_count: ignore all words with total frequency lower than this
		iterations: number of iterations (epochs) over the corpus
		'''
		# all other default parameters are left unchanged
		dm = 0 
		size = self.size 
		negative = 5
		min_count = self.min_count 
		iterations = self.iterations 
		params = {
			'dm': dm,
			'size': size,
			'iter': iterations,
			'negative': negative,
			'min_count': min_count,

		}
		return params
	
	def _tagged_docs(self, doc_set):
		'''
		Return a tagged list of sentences tokenized into words.

		Each senteces has a unique UUID tag. These tags are later used
		for reverse sentence lookup.  
		'''
		TaggedDocuments = namedtuple('TaggedDocuments', 'words tags')
		tagged_docs =[]
		for sent in doc_set.iterator():
			doc = self.nlp(sent.sentence)
			words = []
			# tokenize the sentence/s into words and remove any punctuations
			for s in doc.sents:
				for token in s:
					if not token.is_punct:
						words.append(token.lower_)
			tagged_docs.append(TaggedDocuments(words=words, tags=[sent.tag]))
		return tagged_docs

	def train_d2v_model(self, path=False, new_model=False):
		'''
		Load doc2vec models if they've already been trained for a given 
		FRSKU or train a new set otherwise.
		'''
		then = time()
		NEW_MODEL = False
		d2v_model = None
		try:
			d2v_model = Doc2Vec.load(self.d2v_model_path)
			msg = 'Loaded existing doc2vec model for FRSKU={}'
			msg = msg.format(self.frsku)
		except IOError:
			if new_model:
				self._initialize_nlp()
				doc_set = self._get_documents(d2v_training=True)
				if not doc_set:
					self.dependency()
					doc_set = self._get_documents(d2v_training=True)
				self.doc_list = self._tagged_docs(doc_set)
				msg = 'Training a new doc2vec model for FRSKU={}...'
				logger.info(msg.format(self.frsku))
				d2v_model = self._train()
				NEW_MODEL = True
			else:
				msg = 'doc2vec model does not exist for FRSKU={}. '
				msg += 'Call train_d2v_model with new_model=True to proceed.'
				logger.info(msg.format(self.frsku))
		now = time()
		diff = now - then
		if NEW_MODEL:
			msg = 'New doc2vec model training time for FRSKU={}: {}'
			msg = msg.format(self.frsku, timedelta(seconds=diff))
		logger.info(msg)
		self.d2v_model = d2v_model

	def _train(self):
		'''
		Train a doc2vec model using the PV-DBOW (probability vectors - 
		distributed bag of words) algorithm. 

		We set dm=0 to disable distributed memory alogrithm. 
		dm=1 gave us vector inferences that made no sense. However,
		PV-DBOW gives us exactly what we want even though the actual 
		probability of the predicitons is 0.60 - 0.65. Predictions up to 0.90
		are possible with optimized, i.e. less ambiguous, match query.
		'''
		params = self._get_training_params()
		d2v_model = Doc2Vec(**params)
		d2v_model.build_vocab(self.doc_list)
		EPOCHS = params.get('iter')
		alpha = 0.025
		min_alpha = 0.001
		alpha_delta = (alpha - min_alpha) / EPOCHS
		for epoch in range(EPOCHS):
			random.shuffle(self.doc_list)
			d2v_model.alpha, d2v_model.min_alpha = alpha, alpha
			train_params = {
					'total_examples': d2v_model.corpus_count,
					'epochs': d2v_model.iter
			}
			d2v_model.train(self.doc_list, **train_params)
			alpha -= alpha_delta

		# save the model to disk
		d2v_model.save(self.d2v_model_path)
		msg = 'Saved new doc2vec models for FRSKU={}'
		logger.info(msg.format(self.frsku))
		return d2v_model

	def infer_vectors(self, topic, topn=5, steps=100000):
		'''
		Query the trained model to infer vectors for an unseen sentence 
		and return a list of sentence tags and their probabilities. Later on,
		SentencePrediction will make use of the tags for reverse sentence 
		lookup.

		arguments:
			steps: number of iterations (?); tested step=1 to step=10e6. 10e5
					is optimal
			topn: number of top n sentences to return; n is determined 
					empirically based on the quality of the predictions 
					generated at or above a given probability threshold. Refer 
					to SentencePrediction for more details. 
		'''
		msg = 'Sentence vector inference in progress'
		logger.info(msg)
		topic_words = topic.split()
		inference = self.d2v_model.infer_vector(topic_words,steps=steps)
		sims = self.d2v_model.docvecs.most_similar([inference], topn=topn)
		return sims