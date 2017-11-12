import ml.discourse.summarizer as summ 
import ml.models as m_models
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class AspectRating(summ.Summarize):
	'''
	Performs computation of aspect rating on product aspects. 

	The aspects have already been determined through LDA topic prediction. 
	The calculation utilizes the review rating in which the predicted 
	sentences are found. The rationale behind this approach is that 
	the rating given by the customer for the whole review is an implicitly 
	weighted average of the aspects the customer discusses in the review.
	This approach is modeled after one taken by several papers in the 
	literature.

	There is an error associated with our calculated values but it is mostly
	due to errors in our doc2vec sentence prediction. This can be improved 
	easily with less sparse data.
	'''

	def __init__(self, **kwargs):
		super(AspectRating, self).__init__(**kwargs)
		self.aspect_rating_exists = self._rating_exists()

	def _rating_exists(self):
		EXISTS = m_models.AspectRating.objects.filter(frsku=self.frsku).exists()
		return EXISTS


	def aspect_rating(self):
		'''
		Compute aspect ratings by taking the average of all the parent reviews
		in which the predicted topic sentences are found. 

		NB: If multiple sentences are predicted from the same review, that 
			review will have a greater weight in the averaging process. However,
			we're not applying any weights here because each review is a 
			summation element, i.e, its frequency is already accounted for. 
			Also, we cannot take a straight up average of these averages later 
			on when calculating our own version of the overall product rating 
			in MetadataGenerator because our data would have three separate 
			dimensions at that stage--topic_rank, avg_rating, and frequency. 
			We turn the data into a two-dimensional one by weighting avg_rating 
			by frequency/sum_of_frequencies. 

		The algorithm works as follows:
			1. Get all the sentences making up each topic and call this 
				set topic_set
			2.  For each sentence in topic_set, get the rating of its parent 
				review
			3. Take an arithmetic mean of the ratings 
			4. Repeat for each topic 
			5. Refer to MetadataGenerator for how Adjusted Product Rating is 
				determined
		'''
		if not self.aspect_rating_exists or self.clear_db:
			rating_dict = {}
			if self.clear_db:
				m = m_models.AspectRating.objects.filter(frsku=self.frsku)
				m.all().delete()
			for i in range(self.lda_topic_count):
				try:
					topic_rank = i+1
					topic_set = self.sent_set.filter(topic_rank=topic_rank)
					rating_list = [obj.review_rating for obj in topic_set]
					count = len(rating_list)
					average_rating = round(sum(rating_list)/float(count), 1)
					entry = {
						'frsku': self.frsku,
						'topic_rank': topic_rank,
						'frequency': count,
						'label': topic_set[0].label,
						'avg_rating': average_rating,
					}
					m = m_models.AspectRating.objects.create(**entry)
				except IndexError as e:
					msg = '{}: {}'.format(type(e).__name__, e.args[0])
					logger.exception(msg)
				except ZeroDivisionError as e:
					# zero division only happens when topic_rank has 
					# no corresponding sentences
					msg = '{}: {}'.format(type(e).__name__, e.args[0])
					logger.error(msg)
				except Exception as e:
					msg = '{}: {}'.format(type(e).__name__, e.args[0])
					logger.exception(msg)
			msg = 'Computed aspect ratings for FRSKU={}'.format(self.frsku)
			logger.info(msg)
		else:
			msg = 'Aspect Ratings already exist for FRSKU={}. '
			msg += 'Please try again with clear_db=True\n'
			logger.info(msg.format(self.frsku))

