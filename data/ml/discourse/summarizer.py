import ml.models as m_models
import services.common_helper as ch
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class Summarize(object):
	'''
	Performs summarization on a body of text. The text has 
	already been prepared for us in previous steps. We are simply taking 
	the sentences and formatting them in a logical order. 

	In theory, the summary generated here should be more accurate than
	state-of-the-art extractive summarization techniques like Latent Semantic
	Analysis (LSA), LexRank, or TextRank. These summarization techniques 
	are probabilistic. They use the location of the sentence in a body of
	text to predict its importance. This process does not allow for the
	understanding of the semantic relation between words, sentences, and
	paragraphs. However, because they take a centroid-based approach 
	in generating the final summary, they might perform well (but not 
	necessarily better than doc2vec) on structured data like books, 
	magazine articles, or any other properly vetted media. Conversely, 
	they might fail ungracefully on Twitter and other informal data. 

	Unlike the above techniques, doc2vec tries to build a semantic relation
	between the documents by mapping each document into a vector space of 
	a specified number of feature dimentions (100 in our case). This allows 
	for discovering relations that aren't explictly stated. We've also 
	significantly reduced the work that we would have had to do in organizing 
	the summary by pipelining LDA topic predictions into our doc2vec 
	prediction. In terms of suitability, doc2vec is a ideal for product 
	reviews, where structure and formality is more variable than something like 
	a book or a newspaper article. 
	'''
	def __init__(self, **kwargs):
		self.frsku = kwargs.get('frsku')
		self.clear_db = kwargs.get('clear_db')
		self.sent_set = self._get_pred_sents()
		self.lda_topic_count = self._get_topic_count()
		self.summ_exists = self._summary_exists()
		self._clear_db_entry()

	def _clear_db_entry(self):
		if self.clear_db:
			m_models.RawSummary.objects.filter(frsku=self.frsku).all().delete()

	def _summary_exists(self):
		EXISTS = m_models.RawSummary.objects.filter(frsku=self.frsku).exists()
		return EXISTS


	def _get_pred_sents(self):
		'''
		Return a set of predicted senteces sorted by their LDA topic rank.
		'''
		sent_set = m_models.PredictedSent.objects.filter(frsku=self.frsku)
		sent_set = sent_set.order_by('topic_rank')
		return sent_set

	def _get_topic_count(self):
		'''
		Return a count of the predicted number of LDA topics for FRSKU.
		'''
		params = {
			'product__frsku': self.frsku,
		}
		count = m_models.PredictedLDATopic.objects.filter(**params).count()
		return count

	def _get_aspect_rating(self, label):
		'''
		Return asect rating.
		'''
		rating = -1
		params = {
			'frsku': self.frsku,
			'label': label,
		}
		try:
			rating = m_models.AspectRating.objects.filter(**params)[0].avg_rating
		except Exception as e:
				msg = '{}: {}'.format(type(e).__name__, e.args[0])
				logger.exception(msg)
		return rating


	def _get_topical_summ(self, rank):
		SENT_COUNT = 50
		topical_summ = ''
		label = ''
		aspect_rating = -1
		try:
			topic_set = self.sent_set.filter(topic_rank=rank)
			topic_set = topic_set.order_by('raw_sent_rank')
			label = topic_set[0].label
			aspect_rating = self._get_aspect_rating(label)
			topical_summ += 'Aspect {}: {}\n'.format(rank, label)
			for i in range(SENT_COUNT):
				sentence = topic_set[i].raw_sent.encode('utf-8')
				topical_summ += '{}. {}\n'.format(i+1, sentence)
		except IndexError:
			pass
		kwargs = {
			'aspect': label,
			'topic_rank': rank,
			'aspect_rating': aspect_rating,
			'topical_summ': topical_summ,
		}
		return kwargs

	def _get_master_summ(self, master_summ, topical_summ):
		if topical_summ:
			master_summ += topical_summ
			master_summ += '-------------------------------------------\n\n'
		return master_summ

	def _save_raw_summary(self, master_summ):
		'''
		Save a master summary to the database consisting of all the topical 
		summaries formatted to our liking.
		'''
		params = {
			'frsku': self.frsku,
			'summary': master_summ,
		}
		parent = m_models.RawSummary.objects.create(**params)
		msg = 'Saved raw summary for FRSKU={} to db'.format(self.frsku)
		logger.info(msg)
		return parent

	def _save_topical_summary(self, topical_summary_dict, parent):
		'''
		Save topical summaries individually for embedding into general summary 
		display in the admin dashboard.
		'''
		msg = 'Populating TopicalSummary table for FRSKU={}'
		msg = msg.format(self.frsku)
		logger.info(msg)
		if topical_summary_dict and parent:
			for rank, summary in topical_summary_dict.items():
				summary['raw_summary'] = parent
				ts_obj = m_models.TopicalSummary.objects.create(**summary)
				msg = 'Saved new TopicalSummary object for FRSKU={} with pk={}'
				msg = msg.format(self.frsku, ts_obj.id)
				logger.info(msg)
			msg = 'Finished populating TopicalSummary table\n'
		else:
			msg = 'Unable to populate TopicalSummary table for FRSKU={}. '
			msg += 'Bulk topical summary dict or parent object is missing.\n'
			msg = msg.format(self.frsku)
		logger.info(msg)

	def summarize(self):
		'''
		Get the top 50 most probable sentences for every topic and write 
		it to db as a single string.

		Summarization is the penultimate step in the fooreview process. We use 
		the summaries generated in this step to write our original analysis of 
		the reviews in a way that resembles professional product reviews. There 
		is a level of subjectivity involved in the final selection of the 
		topical summary components but the rest of the process remains largely 
		objective. 

		In the summarization process, topic ranking is not a factor. However, 
		reliability, i.e. doc2vec frequency value after removing sentences 
		with less than 50% probability, is, albeit implicitly. This means
		we're only concerned with the rating for sorting. Reliability comes
		into play when analyzing the summaries: more reliable topics are likely
		to have a more complete summary and therefore more likely to provide 
		a fuller picture when writing the analysis.

		The selection of analysis components is  subjective, i.e. we have to 
		decide whether the topics are something people would care about. 
		As such, this step takes precedence over the quantitative steps. 
		In the end, our analysis takes the following form:
			1. abstraction of each topical summary 
			2. attempt to capture the wide range of sentiments expressed
				throughout the summary (e.g. a highly rated topic could have 
				both positive and negative opinions. Our analysis should take
				those into account)
		'''
		if not self.summ_exists:
			master_summ = ''
			topical_summary_dict = {}
			for i in range(self.lda_topic_count):
				kwargs = self._get_topical_summ(i+1)
				topical_summ = kwargs.pop('topical_summ')
				rank = kwargs.get('topic_rank')
				if topical_summ:
					master_summ = self._get_master_summ(master_summ, topical_summ)
					kwargs['summary'] = topical_summ
					topical_summary_dict[rank] = kwargs
			parent = self._save_raw_summary(master_summ)
			self. _save_topical_summary(topical_summary_dict, parent)
		else:
			msg = 'RawSummary already exists for FRSKU={}. '
			msg += 'Please try again with clear_db=True'
			logger.info(msg.format(self.frsku))

	def _write_to_file(self, **kwargs):
		for summ_name, summ_set_list in kwargs.items():
			for obj in summ_set_list[0]:
				if summ_name == 'master_raw':
					filename = summ_set_list[1] + 'raw_summary.txt'
				else:
					file_id = 'aspect_{}_rating_{}_final_rank_{}'
					filename = summ_set_list[1] + file_id
					filename = filename.format(obj.aspect, obj.aspect_rating,
											 obj.final_rank)
					filename = filename.replace('.','').replace(' ', '~')
					filename = filename + '.txt'
				with open(filename, 'w') as f:
					f.write(obj.summary.encode('utf-8'))
					msg = 'Outputted raw summary file with filename={}'
					msg = msg.format(filename)
					logger.info(msg)

	def summary_to_file(self):
		'''
		Output raw summary files for analysis. 

		We're outputting three groups of files for convenience. 
			Group 1: A master summary that includes all the topical summaries 
					in a single file
			Group 2: Individual files for each topical summary 
			Group 3: Individual files for each topical summary that has been 
					marked as analysis_component

			Group 1 and 2 are reference only and are in txt format. Group 3 is 
			the actual set we use to analyze and write the draft. This group is 
			in docx or Google Docs format. 
		'''
		path_frsku = 'file_dump/summary/{}/'.format(self.frsku)
		path_dict = {
			'frsku': path_frsku,
			'raw': path_frsku + 'raw/',
			'topical_raw': path_frsku + 'topical_raw/',
			'topical_anl': path_frsku + 'topical_anl/',
		}
		for name, path in path_dict.items():
			ch.make_directory(logger, path)
		raw = {'frsku': self.frsku}
		traw = {'raw_summary__frsku': self.frsku}
		tanl = {
					'raw_summary__frsku': self.frsku, 
					'analysis_component': True, 
				}
		master_summ_set = m_models.RawSummary.objects.filter(**raw)
		topical_raw_set = m_models.TopicalSummary.objects.filter(**traw)
		topical_anl_set = m_models.TopicalSummary.objects.filter(**tanl)
		
		kwargs = {
			'master_raw': [
					master_summ_set,
					path_dict.get('raw'),
			],
			'topical_raw': [
					topical_raw_set,
					path_dict.get('topical_raw'),
			],
			'topical_anl': [
					topical_anl_set,
					path_dict.get('topical_anl'),
			],

		}
		self._write_to_file(**kwargs)