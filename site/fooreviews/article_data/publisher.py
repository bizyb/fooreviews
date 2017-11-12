import fooreviews.models as f_models
import glob
import ml.models as m_models
import os
import services.common_helper as ch
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class ArticlePublisher(object):
	'''
	Publishes the final draft of an article. 

	ArticlePublisher is the first step in our migration from fr_data to 
	fr_site. In fr_data, we do all the processing, learning, and 
	computation of our data. In the end, we generate two groups of data:
			Summary - consists of three folders:
						1. Master raw summary 
						2. Topical raw summary 
						3. Topical analysis summary 
			We're only interested in #3 in fr_site. The rest of the summaries 
			are there as a reference. 

			Data, Product, and ProductRaw
					The Data table JSON contains quantitative data for plotting.
					Product and ProductRaw JSONs have no new information since 
					they were imported into fr_data. The only change is updates
					to status fields. (It's not entirely necessary to import 
					entries back into fr_site but it's probably best to keep 
					them consistent across the two servers).

	We call ArticlePublisher through management command from the console. The 
	way it works is as follows:
		1. We upload all the JSONs from fr_data to their respective tables in 
			fr_site
		2. We upload the summary files to their respective directory in fr_site
		3. We take topical analysis summary files (one file per product topic)
			and write our analysis in Microsoft Word or Google Docs. We save 
			the proofread and spell-checked files in .txt format, keeping the 
			filenames the same as the raw files (we don't need to make any 
			changes to the format or filename if using Google Docs).
		4. We place the raw summaries in one folder and the analysis in 
			another. 
		5. ArticlePublisher takes each analysis file and parses the file name 
			to construct a data structured expected by FormatArticle. 
		6. ArticlePublisher places all the formatted analyses in a single 
			dictionary and creates a new models.Article object (we don't create 
			the article manually). It then gives the article a temporary name 
			and save the analyses in its JSON field.
	---------------------------------------------------------------------------- 
	The rest of what follows is further steps in the publication process but 
	they don't get executed until we click the checkbox to indicate publication
	(and thereby disable draft mode). Doing so sends a signal to Elasticsearch 
	to index the article. Indexed articles become available on the main website.
	(Conversely, entering draft mode after publishing deletes them from the 
	index). Once an article has been indexed, loading its URL for the first time 
	calls views.py, which calls the following classes. At this stage, the 
	following things happen:
						a. SEO metadata generated (we still need to write image 
							alt tags manually and test social share links)
						b. GraphingData is called and makes use of the Data 
							table entry to format all the plotting data for the
							given FRSKU, i.e. article. Data formatted for 
							Highcharts gets cached in its proper table (if we 
							delete HighchartsFormattedData entry, we lose the 
							color selection we made but the data gets 
							regenerated the next time we load the page. To 
							enable color selection again, we have to go back 
							to the Data entry and unlock the colors. Colors for 
							sentiment plot, donuts, etc. are always locked 
							by default. If we unlock them as well, they'll 
							be computed again along with the rest of the colors.
							However, because they depend on the quantitative 
							values contained in Data, they'll revert to their 
							original color). 
						
		7. FormatArticle is later called by ArticleDetailView and fills in 
			the missing data such as rating star images, pricing, etc. Refer 
			to FormatArticle for more info.
		8. At this point, all the automated parts of article publication are 
			done (it should take no more than 5 seconds to go through all the 
			steps above). The remaining steps involve giving the article a
			catchy name, completing in-page SEO with image alt tags, writing 
			extended captions for all the plots, and testing share links.
			(NB: The Article title must given before Elasticsearch indexing. The 
			title slugs become the permanent URL of the article. Therefore, it's 
			imperative that we don't slack off on that).
		9. Once everything is functional, we need to migrate the data from
			staging to production.    
	'''

	def __init__(self, frsku, *args, **kwargs):
		self.frsku = frsku
		self.data = self._get_data_obj()
		self.all_files = self._get_files()

	def _get_data_obj(self):
		data_obj = m_models.Data.objects.filter(frsku=self.frsku)
		if data_obj.exists():
			data_obj = data_obj[0]
			return data_obj.data
		else:
			msg = 'No Data entry exists for FRSKU={}'
			msg = msg.format(self.frsku)
			logger.info(msg)

	def _get_files(self):
		'''
		Get all topical anlysis summary files. If the directory doesn't exist,
		create it. 
		'''
		all_file_names = []
		topical_anl_path = 'file_dump/summary/{}/topical_anl/'
		topical_anl_path = topical_anl_path.format(self.frsku)
		ch.make_directory(logger, topical_anl_path)
		file_path = topical_anl_path + '/*.txt'
		all_file_names = [filename for filename in glob.glob(file_path)]
		return all_file_names
		
	def _sort_filenames(self, parsed_filenames):
		'''
		Return a sorted list of filename objects. Sorting is done on aspect 
		rating in descending order. This determines the order in which topical
		analysis sections are displayed in the main article. 
		'''
		# we can use numpy and its cryptic api or just implement our own here
		# build a 2-column list
		to_be_sorted = []
		sorted_file_names = []
		for pf_dict in parsed_filenames:
			rating = pf_dict.get('aspect_rating')
			topic = pf_dict.get('topic')
			to_be_sorted.append((rating, topic))
		sorted_names = sorted(to_be_sorted, reverse=True) # descending
		for s in sorted_names:
			for pf_dict in parsed_filenames:
				rating = pf_dict.get('aspect_rating')
				topic = pf_dict.get('topic')
				if rating == s[0] and topic == s[1]:
					sorted_file_names.append(pf_dict)
		return sorted_file_names

	def _parse_filename(self):
		'''
		Parse the filename of a topical anlysis file and get the following 
		data structure:
		all_parsed = [	
						{
							filename: xyz,
							topic: aspect name,
							aspect_rating: 4.4,
							final_rank: 22,
							},
						...
					]
		'''
		all_parsed = []
		for path in self.all_files:
			# eg1 = 'aspect_Compartments_rating_35_final_rank_13.txt'
			# eg2 = 'aspect_Build~Material_rating_33_final_rank_14.txt'
			f = path.split('/')[-1].replace('.txt', '')
			tokens = f.split('_rating_')
			topic = tokens[0].split('aspect_')[-1].replace('~', ' ')

			# a topic may have an accidental double spacing; remove it 
			topic = ' '.join([token for token in topic.split() if token])
			
			aspect_rat = tokens[-1].split('_')[0]
			aspect_rat = float(aspect_rat)/10.0
			final_rank = tokens[-1].split('_')[-1]

			# final_rank is not used at this stage or beyond but we'll keep 
			# it in case we need it 
			parsed = {
				'filename': path,
				'topic': topic,
				'aspect_rating': aspect_rat,
				'final_rank': final_rank,
			}
			all_parsed.append(parsed)
		all_parsed = self._sort_filenames(all_parsed)
		return all_parsed
		

	def _get_sentiment_color(self, rating, topic_name, rank):
		#NB: colors won't be populated in the Data table until we've publsished
		# an empty article; we can delete the article and try to publish it 
		# again from here, which sould assign the proper aspect colors then;
		# otherwise, the call to _get_sentiment_color() will fail
		aspect_ratings = self.data.get('Aspect Rating')
		for aspect_dict in aspect_ratings:
			asp_rating = aspect_dict.get('Aspect Rating')
			asp_name = aspect_dict.get('Aspect')
			asp_rank = aspect_dict.get('Rank')
			asp_color = aspect_dict.get('color')
			if topic_name == asp_name and rating == asp_rating:
				return asp_color


	def _build_topical_obj(self, file_dict):
		'''
		Build a topical analysis object that contains the following attributes:
			1. Topic 
			2. Aspect rating
			3. Analysis text
			4. Color 
			5. Aspect star rating*
			6. Anchor tag*

			Color refers to the calculated color and transparency value found 
			in the Data table for the aspect rating. This is the color given to 
			the bubbles in the sentiment plot. In the article, we color code the 
			left border of each topical analysis section to match the bubble 
			color. Because the topics are sorted from highest-rated to lowest-
			rated aspect, this gives a sense of visual symmetry on how we split 
			the text. 

			 Aspect start rating refers to star icons corresponding to the 
			 aspect rating. The image is generated dynamically by FormatArticle. 

			 Anchor tag refers to the slugified version of the topic name. It 
			 is used in the main article for table of contents. Because the 
			 article can get long, it provides an intuitive internal navigation.
			 When someone clicks on a table of contents element, the view 
			 automatically skips to that section of the page. The implementation 
			 of this behavior is encoded in the html template for detailview. 

			 * both #5 and 6 are populated by FormatArticle.

			 At this point, it should be obvious that ArticlePublisher is really
			 just creating the scaffolding of an article that various modules 
			 populate. In the end, the remaining fields need to be written in 
			 manually because they cannot be automated. 
		'''
	
		topical_obj_dict = {}
		rating = file_dict.get('aspect_rating')
		topic_name = file_dict.get('topic')
		aspect_rank = file_dict.get('final_rank')
		filename = file_dict.get('filename')
		color = self._get_sentiment_color(rating, topic_name, aspect_rank)
		text = ''
		with open(filename, 'r') as f:
			sentences = f.readlines()
		
		TOP_N = 5 # get the first 5 sentences
		text = [sent.replace('\n', '') for sent in sentences[:TOP_N]]
		text = ['<li>' + sent + '</li>' for sent in text]
		text = ' '.join(text)
		lexrank_summary = '<ul>' + text + '</ul>'
		
		topical_obj_dict = {
			topic_name: {
					'color': color,
					'aspect_rating': rating,
					'summary': lexrank_summary,
					'aspect_star_rating': '',
			}
		}
		return topical_obj_dict

	def _create_article(self, content):
		lookup = {'product__frsku': self.frsku}
		article_set = f_models.Article.objects.filter(**lookup)
		if article_set.exists():
			# If there is an existing article, update it. Save each individual 
			# object so it gets re-indexed by Elasticsearch
			for obj in article_set:
				obj.content = content
				obj.save()
				msg = 'Updated article content for article with pk={}'
				msg = msg.format(obj.id)
				logger.info(msg)

		else:
			# NB: Our entry does not contain article title; we'll have to create
			# it manually
			parent = f_models.Product.objects.filter(frsku=self.frsku)[0]
			entry = {
					'product': parent,
					'content': content,

			}
			article = f_models.Article.objects.create(**entry)
			msg = 'Created a new article with pk={}'
			msg = msg.format(article.id)
			logger.info(msg)

	def publish(self):
		'''
		Build an article containing all topical analysis sections and their 
		respective attributes. In order to publish the article, create a new 
		a new article object if one doesn't exist. Otherwise, update the content 
		field of an existing article.

		article_content: Note the structure of the JSON/dictionary. It's a one-
		element dictionary whose value is a list containing topical 
		dictionary items. This sort of structure guarantees our sorting. However,
		it complicates parsing out the data in the template. This is reflected 
		in the nested for loops just to get to the individual topical 
		dictionary objects.    
		'''
		content = []
		file_objects = self._parse_filename()
		for fo in file_objects:
			topical_dict = self._build_topical_obj(fo)
			content.append(topical_dict)
		article_content = {self.frsku: content}
		self._create_article(article_content)

	