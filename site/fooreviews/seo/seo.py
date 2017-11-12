import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()
class SEOMetaTags(object):
	'''
	Standardizes meta tag data for all view types so they may all
	conform to Open Graph, Twitter Cards, and Schema.org, which are used 
	by Facebook and LinkedIn, Twitter, and Google+, respectively.

	Available view types:
		DetailView
		Index
		About
		Methodology
		Contact Us
		Terms
		Privacy
		SearchListView
		CategoryListView


		# TODO: schema.org for 
			- review star rating,
			- review count (only hams, no spam or duplicats); need to get this in article_data.py
			- breadcrumbs,
			- article created date,
			-
	'''
	def __init__(self, context, **kwargs):
		self.context = context
		self.view_type = context.get('view_type')
		self.site_name = '| Fooreviews'
		self.default_title = '''Product Review Analysis {}'''.format(self.site_name)
		self.generic_views = [
								'FRSKU',
								'Index',
								'About',
								'Terms',
								'Privacy',
								'Interpretation',
								'Contact Us',
								'SearchListView',
								'CategoryListView',

							]

	def _get_detail_title(self):
		'''
		Return a parameterized DetailView title that shows the article 
		title.
		'''
		article_obj = self.context.get('article')
		detail_title = self.default_title
		if article_obj:
			detail_title = '{} {}'.format(article_obj.article_title, self.site_name)
		return detail_title

	def _get_cat_title(self):
		'''
		Return a parameterized CategoryListView title that shows the breadcrumb.
		'''
		# a breadcrumb_obj is a list of tuples, where each tuple has the 
		# breadcrumb at [0] and margin offset (not used anymore) at [1]
		cat_title = self.default_title
		breadcrumb_obj = self.context.get('breadcrumb_obj')
		if breadcrumb_obj:
			breadcrumb_list = breadcrumb_obj[-1]
			
			# get the node element
			node_dict = breadcrumb_list[0]
			node_name = node_dict.keys()[0]
			cat_title = 'Reviews for {} {}'.format(node_name, self.site_name)
		else:
			cat_title = 'Reviews for All Topics {}'.format(self.site_name)
		return cat_title

	def _get_search_title(self):
		query = self.context.get('q')
		search_title = 'Results for \'{}\' {}'.format(query, self.site_name)
		return search_title

	def _get_meta_title(self):
		'''
		Return page title.
		'''

		if self.view_type in ['Index', 'FRSKU']:
			meta_title = self.default_title
		elif self.view_type == 'About':
			meta_title = 'About {}'.format(self.site_name)
		elif self.view_type == 'Interpretation':
			meta_title = 'Making Sense of Our Data {}'.format(self.site_name)
		elif self.view_type == 'Contact Us':
			meta_title = 'Contact Us {}'.format(self.site_name)
		elif self.view_type == 'Terms':
			meta_title = 'Terms of Service {}'.format(self.site_name)
		elif self.view_type == 'Privacy':
			meta_title = 'Privacy Policy {}'.format(self.site_name)
		elif self.view_type == 'DetailView':
			meta_title = self._get_detail_title()
		elif self.view_type == 'CategoryListView':
			meta_title = self._get_cat_title()
		elif self.view_type == 'SearchListView':
			meta_title = self._get_search_title()
		return meta_title

	def _get_meta_desc(self):
		'''
		Return generic meta tags that will be used on pages whose content doesn't change often.  
		'''
		default_meta_desc = 'Fooreviews uses machine learning to analyze '
		default_meta_desc += 'thousands of reviews for people who want a thorough ' 
		default_meta_desc += 'overview so they can buy the best product'

		if self.view_type in self.generic_views:
			meta_desc =  default_meta_desc
		elif self.view_type == 'DetailView':
			article_obj = self.context.get('article')
			meta_desc = article_obj.meta_description
		return meta_desc


	def _get_meta_image(self):
		'''
		Return a meta image to be displayed as a social share thumbnail.
		'''	
		default_meta_image = '/static/img/logo400.jpg'
		if self.view_type in self.generic_views:
			meta_image = default_meta_image
		elif self.view_type == 'DetailView':
			meta_image = default_meta_image
		return meta_image


	def get_meta_tags(self):
		'''
		Update and return a context dictionary with a complete list of 
		SEO meta tags.

		NB: Canonical URL is also a meta tag but we don't pass it here. The template 
		does a good job of handling that itself.
		'''
		try:
			context_meta = {
				'meta_title': self._get_meta_title(),
				'meta_desc': self._get_meta_desc(),
				'meta_image': self._get_meta_image(),
			}
			self.context.update(context_meta)
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)
		return self.context

		









