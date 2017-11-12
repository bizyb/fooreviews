from ml import models as m_models

class AspectRating(object):
	'''
	'''
	def __init__(self, **kwargs):
		self.frsku = kwargs.get('frsku')

	def get_aspect_rating(self):
		ratings_dict = {}
		for topic, sent_list in sent_dict.items():
			rating_sum = 0.0
			for sent in sent_list:
				params = {
						'sentence__contains':sent,
					}
				try:
					sent_obj = m_models.SentenceTable.objects.filter(**params)[0]
					rating = sent_obj.review.rating
					if not isinstance(rating, float):
						rating = 0.0
						# log failure here
					rating_sum += rating
				except Exception as e:
					pass
			avg_rating = rating_sum/float(len(sent_list))
			ratings_dict[topic] = average
		return ratings_dict

class Sentiment(object):
	'''
	Converts numerical ratings to qualitative sentiments.
	'''
	def __init__(self, **kwargs):
		self.frsku = kwargs.get('frsku')

	def _rating_to_sentiment(self, rating):
		sentiment = 'Unknown'
		rating = float(rating)
		# TODO: ASSERT that rating is between 0.0 and 5.0
		if rating > 4.4:
			sentiment = 'Highly Positive'
		elif rating > 3.4:
			sentiment = 'Positive'
		elif rating > 2.4:
			sentiment = 'Neutral'
		elif rating > 1.4:
			sentiment = 'Negative'
		else:
			sentiment = 'Highly Negative'
		return sentiment



