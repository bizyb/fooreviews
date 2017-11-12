import copy
import parsers.models as p_models
import ml.models as m_models
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class MetadataGenerator(object):
	'''
	Generates review metadata based on the results of nlp processing 
	and ml analysis. The data generated here are used in making plots
	for front-end publication.

	Some of the data are already available in the their respective db 
	tables in the format we want. Nevertheless, we will query them here and 
	consolidate them into a single table for a given FRSKU so we can serve 
	them through AJAX calls.
	'''
	def __init__(self, **kwargs):
		self.frsku = kwargs.get('frsku')
		self.clear_db = kwargs.get('clear_db')
		self.aspect_set = self._get_queryset('aspect_rating')
		self.topical_summ_set = self._get_queryset('topical_summary')
		self.pred_topic_set = self._get_queryset('pred_topics')
		self.reranked_topics = self._rerank_topics()
		self.raw_rev_count = 0
		self.mapped_rev_count = 0
		self.mapped_ham_set = self._get_mapped_set()
		
	def _get_queryset(self, qset_type):
		tables = {
			'aspect_rating': m_models.AspectRating,
			'topical_summary': m_models.TopicalSummary,
			'pred_topics': m_models.PredictedLDATopic,
		}
		instance = tables.get(qset_type)
		if qset_type == 'aspect_rating':
			lookup = {'frsku': self.frsku}
		elif qset_type == 'topical_summary':
			lookup = {'raw_summary__frsku': self.frsku}
		elif qset_type == 'pred_topics':
			lookup = {'product__frsku': self.frsku}
		qset = instance.objects.filter(**lookup)
		if qset_type in ['aspect_rating', 'topical_summary']:
			qset = qset.order_by('topic_rank').distinct('topic_rank')
		elif qset_type == 'pred_topics':
			qset = qset.order_by('rank').distinct('rank')
		return qset

	def _get_mapped_set(self):
		'''
		Return a ham/spam classified mapped review set.
		'''
		frsku_key = 'review_raw__crawl_cache__crawl_queue__product_raw'
		frsku_key += '__product__frsku'
		self._classify_revs()
		params_mapped = {
			'unique': True,
			'ham': True,
			frsku_key: self.frsku,
		}
		mapped_ham_set = m_models.AnalysisCorpus.objects.filter(**params_mapped)
		if not mapped_ham_set:
			msg = 'Could not find any reviews with classification ham=True '
			msg += 'for FRSKU={}'
			msg = msg.format(self.frsku)
			logger.info(msg)
		return mapped_ham_set

	def _rerank_topics(self):
		'''
		Assign new ranks to predicted LDA topics to address the issue of gaps 
		that may have risen after removing low-probability topics during summary 
		generation. 

		Reranked values are used wherever the rank is shown
		explicitly in the front-end
		'''
		m = m_models.RerankedTopic.objects.filter(frsku=self.frsku)
		EXISTS = m.exists()
		if not EXISTS:
			for index, obj in enumerate(self.topical_summ_set):
				old_rank = obj.topic_rank
				new_rank = index + 1
				entry = {
					'old_rank': old_rank,
					'new_rank': new_rank,
					'frsku': self.frsku,
				}
				m_models.RerankedTopic.objects.create(**entry)
				obj.final_rank = new_rank
				obj.save()
			msg = 'Reranked LDA topics for FRSKU={}'.format(self.frsku)
		else:
			msg = 'Reranked topics already exist in RerankedTopic for FRSKU={}'
			msg = msg.format(self.frsku)
		return m_models.RerankedTopic.objects.filter(frsku=self.frsku)
		logger.info(msg)


	def _classification(self):
		'''
		Return counts of different review classifications.
		'''
		ham_count = self.mapped_ham_set.count()
		spam_count = self.mapped_rev_count - ham_count
		dup_count = self.raw_rev_count - self.mapped_rev_count
		classified_dict = {
			'Duplicate': {'review_count':dup_count },
			'Spam': {'review_count': spam_count} ,
			'Legitimate': {'review_count': ham_count},
		}
		return classified_dict

	def _get_review_set(self):
		frsku_key = 'crawl_cache__crawl_queue__product_raw__product__frsku'
		params_raw = {
				'ml_mapped': True,
				frsku_key: self.frsku,
				'is_training_data': False,
		}
		frsku_key = 'review_raw__crawl_cache__crawl_queue__product_raw'
		frsku_key += '__product__frsku'
		params_mapped = {
				'unique': True,
				frsku_key: self.frsku,
		}
		raw_rev_set = p_models.ReviewRaw.objects.filter(**params_raw)
		mapped_rev_set = m_models.AnalysisCorpus.objects.filter(**params_mapped)
		raw_rev_count = raw_rev_set.count()
		return raw_rev_count, mapped_rev_set, params_mapped

	def _update_ham_spam(self, anl_rev_obj, ham, spam):
		anl_rev_obj.ham = ham
		anl_rev_obj.spam = spam
		anl_rev_obj.save()
		msg = 'Classified review as spam/ham for AnalysisCorpus obj with pk={}'
		msg = msg.format(anl_rev_obj.id)
		logger.info(msg)

	def _classify_revs(self):
		'''
		Classifiy reviews as spam and ham. 

		Spam reviews are those that were mapped to AnalysisCorpus from 
		ReviewRaw but weren't used in doc2vec model training because 
		they were short on substance.
		'''
		count, mapped_rev_set, params_mapped = self._get_review_set()
		self.raw_rev_count = count 
		self.mapped_rev_count = mapped_rev_set.count()
		params_mapped['ham'] = True
		ham_set = m_models.AnalysisCorpus.objects.filter(**params_mapped)
		if not ham_set.exists():
			# Get mapped reviews from AnalysisCorpus and do reverse lookup to 
			# get all the corresponding sentences from SentenceTable; NB: Each 
			# AnalysisCorpus object will have a queryset consisting of all its 
			# sentence objects. Check if the sentence objects have all passed 
			# NLP. Set to ham if so and spam if otherwise. 
			params_mapped.pop('ham')
			anl_rev_set = m_models.AnalysisCorpus.objects.filter(**params_mapped)
			sent_table_qs_set = [(obj, obj.sent_table_review.all()) \
									for obj in anl_rev_set]
			for anl_obj, sent_qs in sent_table_qs_set:
				if sent_qs.filter(nlp_pass=True).count():
					self._update_ham_spam(anl_obj, True, False)
				else:
					self._update_ham_spam(anl_obj, False, True)
		else:
			msg = 'Reviews have already been classified as spam/ham '
			msg += 'for FRSKU={}'
			msg = msg.format(self.frsku)
			logger.info(msg)

	def  _rating_distro(self):
		'''
		Get a corpus-wide review rating distribution.
		'''
		frsku_key = 'review_raw__crawl_cache__crawl_queue__product_raw'
		frsku_key += '__product__frsku'
		star_count_dict = {}
		MAX_RATING = 5
		params = {
			frsku_key: self.frsku,
			'spam': False,
			'ham': True,
		}
		rev_set = m_models.AnalysisCorpus.objects.filter(**params)
		rev_set = m_models.AnalysisCorpus.objects.filter(**params)
		for i in range(MAX_RATING):
			rating = i+1
			key = '{} Stars'.format(rating)
			if rating == 1:
				key = '{} Star'.format(rating)
			rev_count = rev_set.filter(review_raw__rating=float(rating)).count()
			entry = {'review_count': rev_count}
			star_count_dict[key] = entry
		return star_count_dict
	
	def _adjusted_rating(self):
		'''
		Return an adjusted product rating by taking a weighted average of aspect
		ratings. 
		'''
		freq_list = [obj.frequency for obj in self.aspect_set]
		rating_list = [obj.avg_rating for obj in self.aspect_set]
		sum_freq = sum(freq_list)
		weights = map(lambda x: x/float(sum_freq), freq_list)
		weighted_avg = 0.0
		z = zip(rating_list, weights)
		weighted_avg += sum([float(r)*w for r,w in z]) 
		weighted_avg = round(weighted_avg, 1)
		return weighted_avg # Adjusted Rating

	def _review_count(self, classified_dict):
		'''
		Return raw review count.
		'''
		count = 0
		for k, v in classified_dict.items():
			count += v.get('review_count')
		return count

	def _aspect_count(self):
		'''
		Return a count of product aspects discovered.
		'''
		params = {
			'product__frsku': self.frsku,
		}
		count = m_models.PredictedLDATopic.objects.filter(**params).count()
		return count


	def _aspect_rating(self):
		'''
		Return aspect ratings with normalized weights on 0-1 scale. 
		'''
		master_data_list = []
		aspect_freqs = []
		for aspect_obj in self.aspect_set:
			try:
				params_old = {'topic_rank': aspect_obj.topic_rank}
				params_new = {'old_rank': aspect_obj.topic_rank}
				topical_obj = self.topical_summ_set.filter(**params_old)[0]
				new_rank = self.reranked_topics.filter(**params_new)[0].new_rank
				aspect_data_dict = {
					'Aspect': topical_obj.aspect, # legend/hover
					'Rank': new_rank, # x
					'Aspect Rating': float(aspect_obj.avg_rating), # y
					'Weight': aspect_obj.frequency # z; part of hovering effect
				}
				aspect_freqs.append(aspect_obj.frequency)
				master_data_list.append(aspect_data_dict)
			except Exception as e:
				msg = '{}: {}'.format(type(e).__name__, e.args[0])
				logger.exception(msg)
		normalized_freq_dict = self._normalize_ar_weights(aspect_freqs)
		master_data_list = self._update_ar_weights(master_data_list, \
							normalized_freq_dict)
		return master_data_list

	def _normalize_ar_weights(self, freq_list):
		'''
		Normalize aspect rating weights (frequencies) on a 0-100 scale 
		with respect to the aspect rating with the highest frequency.
		'''
		max_freq = float(max(freq_list))
		normalized_freqs = {}
		for freq in freq_list:
			new_weight = freq/max_freq*100
			if new_weight > 1:
				new_weight = int(new_weight)
			else:
				# round weights less than 1 to two decimal places
				new_weight = round(new_weight, 2)
			normalized_freqs[freq] = new_weight
		return normalized_freqs

	def _update_ar_weights(self, master_data_list, normalized_freq_dict):
		'''
		Update aspect rating weights (frequencies) with the new 
		normalized ones (they're percents but we'll treat them as
		having arbitrary units).
		'''
		data_dict_list = copy.deepcopy(master_data_list)
		for aspect_dict in data_dict_list:
			old_weight = aspect_dict['Weight']
			new_weight = normalized_freq_dict[old_weight]
			aspect_dict['Weight'] = new_weight
		return data_dict_list

	def _topic_distro(self):
		#TODO: refactor this
		'''
		Generate two types of topic distribution: the first is detailed, where
		all proportions are represented. The second is combined, where there 
		are the top 20 proportions and the remaining topics combined into a 
		single proportion. The combined distro is shown alongside the 
		summaries, where each the proportion of each summary topic corresponds 
		to the uncombined distro. The other one is  shown later on as a 
		footnote.

		NB: We're getting the aspect used to label the distro directly from 
		TopicalSummary because the one shown there is the only one applicable 
		to the product, not the one in LDATopic.group_label. The two labels can
		be the same (and they will be in most cases). We anticipate that some 
		future products may require editing the aspect in TopicalSummary to 
		better match the product. Thus, we're letting those aspects take
		precendence because they're the last ones edited before publication. 
		Conversely, we're keeping LDATopic.group_label intact because they 
		apply to the domain in general.
		''' 
		all_distro_list = []
		combined_distro_list = []
		sum_freq_other = 0
		sum_freq_all = 0
		for obj in self.pred_topic_set:
			try:
				# ignore topics that did not make it into RawSummary or 
				# TopicalSummary
				params_old = {'topic_rank': obj.rank}
				topical_obj = self.topical_summ_set.filter(**params_old)[0]
				params_new = {'old_rank':topical_obj.topic_rank}
				new_rank = self.reranked_topics.filter(**params_new)[0].new_rank
				distro_dict = {
					'Aspect': topical_obj.aspect,
					'Distribution': obj.frequency,
				}
				sum_freq_all += obj.frequency
				if not topical_obj.analysis_component:
					sum_freq_other += obj.frequency
				else:
					combined_distro_list.append(distro_dict) # TDS
					distro_dict['summ_component'] = True
				all_distro_list.append(distro_dict) # TDA
			except IndexError:
				pass	
			except Exception as e:
				msg = '{}: {}'.format(type(e).__name__, e.args[0])
				logger.exception(msg)
		
		other_distro = {
			'Aspect': 'Other',
			'Distribution': sum_freq_other,
		}
		combined_distro_list.append(other_distro)

		all_distro_list = self._distro_to_percent(all_distro_list, sum_freq_all)
		combined_distro_list = self._distro_to_percent(combined_distro_list, \
								sum_freq_all)
		return all_distro_list, combined_distro_list

	def _distro_to_percent(self, distro_dlist, denom):
		'''
		Convert raw distribution numbers to percents.
		'''
		new_distro_dlist = copy.deepcopy(distro_dlist)
		for distro_dict in new_distro_dlist:
			for key, val in distro_dict.items():
				if key == 'Distribution':
					# round percents to the nearest tenth place
					percent = round(val/float(denom)*100, 1)
					distro_dict[key] = percent
		return new_distro_dlist
		

	def _get_regression_x_y(self, data_dict):
		x = []
		y = []
		topic_num_list = []
		try:
			x = [unicode(freq_prob[0]) for topic_num, \
							freq_prob in data_dict.items()] #frequency
			y = [unicode(freq_prob[1]) for topic_num, \
							freq_prob in data_dict.items()] # probability
			topic_num_list = [topic_num for topic_num, \
						freq_prob in data_dict.items()]
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)
		return x, y, topic_num_list

	def _get_regression_z(self, topic_num_list):
		z = []
		for i in range(len(topic_num_list)):
			try:
				# replace the old ranks and get an aspect label for each rank
				topic_num = int(topic_num_list[i])
				params = {'topic__topic_num':topic_num}
				pred_obj = self.pred_topic_set.filter(**params)[0]
				old_rank = int(pred_obj.rank)
				old = {'old_rank': old_rank}
				new_rank = int(self.reranked_topics.filter(**old)[0].new_rank)
				new = {'final_rank': new_rank}
				aspect = self.topical_summ_set.filter(**new)[0].aspect
				value = '{}. {}'.format(new_rank, aspect)
				z.append(value)
			except IndexError:
				pass
			except Exception as e:
				msg = '{}: {}'.format(type(e).__name__, e.args[0])
				logger.exception(msg)
		return z

	def _lda_regression(self):
		'''
		Get LDA topic prediction regression data used to rank the topics.

		Values:
			x and y values are plotted on a standard 2-d plane. The z values, 
			however, are not directly plotted. They're values attached to 
			each x-y pair that one can see when hovering over the points.

			We're casting decimal values to unicode due to JSON serialization 
			issues  when saving the final dictionary to db. Remember to cast 
			it back to float or decimal type before plotting.   
		'''
		x,y = 0,0
		params = {'frsku': self.frsku}
		regression_obj = m_models.LDARegression.objects.filter(**params)[0]
		data_dict = regression_obj.data
		x, y, topic_num_list = self._get_regression_x_y(data_dict)
		z = self._get_regression_z(topic_num_list)
		reg_data_dict = {
			'slope': unicode(regression_obj.slope),
			'intercept': unicode(regression_obj.intercept),
			'r_squared': unicode(regression_obj.r_value ** 2),
			'x': x,
			'y': y,
			'z': z,
		}
		return reg_data_dict

	def _review_time_series(self):
		'''
		Generate a time series data. Return a dictionary containing 
		the number of reviews per time period (monthly) per star rating along
		with the total number of reviews for the same time interval.
		'''
		STARS = 5
		master_bucket = {}
		for i in range(STARS):
			rating = i+1
			review_set = self.mapped_ham_set.filter(review_raw__rating=rating)
			if review_set:
				agged_by_day = self._aggregate_by_day(review_set)
				agged_by_month = self._aggregate_by_month(agged_by_day)
				master_bucket[rating] = agged_by_month

		master_bucket['Overall'] = self._combine_aggregates(master_bucket)
		master_bucket = self._populate_gaps(master_bucket)
		return master_bucket


	def _aggregate_by_day(self, review_set):
		'''
		Aggregate reviews by day.
		'''
		bucket = {}
		for obj in review_set:
			date = obj.review_raw.review_date
			if date in bucket:
				bucket[date] += 1
			else:
				bucket[date] = 1
		return bucket

	def _aggregate_by_month(self, agged_by_day):
		'''
		Aggregate review counts that have already been aggregated by day 
		by month.

		The bucket key that we're constructing here is not arbitrary. It 
		corresponds to the input data type (for x-axis) required by 
		whatever visualization tool we'll be using (Highcharts) for time
		series data. 
		'''
		bucket = {}
		for datetime, freq in agged_by_day.items():
			# set the date to mid-month to prevent Highcharts from 
			# defaulting to the previous month 
			DAY = 15 
			year = datetime.date().year
			month = datetime.date().month
			key = '{}/{}/{}'.format(month, DAY, year)
			if key in bucket:
				bucket[key] += freq
			else:
				bucket[key] = freq
		return bucket

	def _combine_aggregates(self, monthly_aggregates):
		bucket = {}
		for rating, agged_by_month in monthly_aggregates.items():
			for date, freq in agged_by_month.items():
				if date in bucket:
					bucket[date] += freq
				else:
					bucket[date] = freq
		return bucket

	def _populate_gaps(self, monthly_aggregates):
		'''
		Normalize aggregations by setting the start and end date and the
		time intervals across them to be the same. Fill in 0 for any time 
		periods lacking frequency values.  
		'''
		all_aggs = monthly_aggregates.pop('Overall')
		for date, combined_freq in all_aggs.items():
			for rating, date_freq in monthly_aggregates.items():
				if date not in date_freq.keys():
					date_freq[date] = 0
		monthly_aggregates['Overall'] = all_aggs
		return monthly_aggregates

	def _verified_purchase(self):
		'''
		Return the number of verified and unverified purchases.
		'''
		params = {'review_raw__verified_purchase':True}
		ver_count = self.mapped_ham_set.filter(**params).count()
		unver_count = self.mapped_ham_set.count() - ver_count
		count_dict = {
			'Verified Purchase': {'review_count': ver_count},
			'Unverified Purchase': {'review_count': unver_count},
		}
		return count_dict

	def _recommend(self):
		'''
		Return a count of reviews that that recommend the product to others.

		NB: Recommendation data not provided by Amazon and eBags. This means 
		when processing product review data from multiple merchants, the 
		proportions should be with respect to the total review count from 
		merchants that provide recommendation data.  

		'''
		params = {'review_raw__recommend_to_friend':True}
		rec_count = self.mapped_ham_set.filter(**params).count()
		unrec_count = self.mapped_ham_set.count() - rec_count
		count_dict = {
			'Recommended': {'review_count': rec_count},
			'Not Recommended': {'review_count': unrec_count},
		}
		return count_dict

	def _helpful(self):
		'''
		Return review helpful/unhelpful count.
		'''
		hf = [obj.review_raw.helpful_count for obj in  self.mapped_ham_set]
		uhf = [obj.review_raw.unhelpful_count for obj in  self.mapped_ham_set]
		helpful_count = sum(hf)
		unhelpful_count = sum(uhf)
		count_dict = {
			'Helpful': {'review_count': helpful_count},
			'Unhelpful': {'review_count': unhelpful_count},
		}
		return count_dict

	def _get_data_functions(self):
		func_dict = {
			'Helpful': self._helpful,
			'Verified Purchase': self._verified_purchase,
			'Recommend': self._recommend,
			'Classification': self._classification,
			'Aspect Rating': self._aspect_rating,
			'Adjusted Rating': self._adjusted_rating,
			'Rating Distribution': self._rating_distro,
			'Regression': self._lda_regression,
			'Time Series': self._review_time_series,
			'Aspects Discovered': self._aspect_count,

		}
		return func_dict

	def _save_data(self, data):
		# clear_db is always true whenever MetadataGenerator is called. 
		# we're keeping the if statement here in case we want to debug
		if self.clear_db:
			m_models.Data.objects.filter(frsku=self.frsku).all().delete()
			msg = 'Cleared Data table for FRSKU={}'
			msg = msg.format(self.frsku)
			logger.info(msg)
		m_models.Data.objects.create(**data)
		msg = 'Saved new plotting data for FRSKU={}'.format(self.frsku)
		logger.info(msg)

	def generate_data(self):
		'''
		Get review data, including metadata and non-metadata. Metadata are
		simple stats that are already part of the review corpus. Non-metadata 
		are those generated as part of the analyis process and are central to 
		the content.

		We have metadata like word count, sentence count, etc. stored in the 
		AnalysisCorpus table. Even though some websites for spotting fake 
		reviews plot data like that, it wouldn't make much sense for us to do 
		the same. The idea behind our data is to provide useful information 
		around which we can write a story.
		'''
		EXISTS = m_models.Data.objects.filter(frsku=self.frsku).exists()
		if not EXISTS or self.clear_db:
			msg = 'Generating plottable data for FRSKU={}'.format(self.frsku)
			logger.info(msg)
			try:
				data_dict = {}
				data_functions = self._get_data_functions()
				for name, func in data_functions.items():
					msg = 'Running data generation step: {}'.format(name)
					logger.info(msg)
					data_dict[name] = func()
				review_count = self._review_count(data_dict['Classification'])
				all_distro, combined_distro =  self._topic_distro()
				data_dict['Reviews Analyzed'] = review_count
				data_dict['Topic Distribution Summ'] = combined_distro
				data_dict['Topic Distribution All'] = all_distro
			except Exception as e:
				msg = '{}: {}'.format(type(e).__name__, e.args[0])
				logger.exception(msg)
			self._save_data({'frsku': self.frsku, 'data': data_dict})
		else:
			msg = 'Plotting data already exists for FRSKU={}'
			msg = msg.format(self.frsku)
			logger.info(msg)
			