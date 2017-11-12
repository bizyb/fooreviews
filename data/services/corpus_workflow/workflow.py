from concurrent.futures import ThreadPoolExecutor
import crawler.analysis.review.review_crawler as review_crawler
import crawler.corpus.corpus.corpus_crawler as crawler
import parsers.corpus.corpus.corpus_parser as corpus_parser
import parsers.corpus.landing.landing_parser as landing_parsrer
import crawler.corpus.url_builder.url_builder as url_builder
import crawler.queue.corpus_queuer as corpus_queuer
import crawler.models as c_models
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class CorpusWorkflow(object):
	'''
	Controls the workflow of corpus crawling and parsing. Instead of crawling 
	the reviews of individual products, we crawl the products themselves. We 
	then take the crawled products, their IDs, review counts, etc. and build 
	crawlable URLs for crawling all product-specific reviews.

	Workflow:
		1. Crawl Landing
		2. Parse Landing
		3. Build URLs 
		4. Crawl Corpus 
		5. Parse Corpus 

		These steps need to be executed once after every new product domain 
		addition. We don't add product domains often (we already have six or 
		so domains that will take us months to populate with articles). 

	'''
	def __init__(self, recrawl=False, **kwargs):

		self.merchant = kwargs.get('merchant')
		self.url_obj = None
		self.THREAD_COUNT = 50
		self.kwargs = kwargs
		self.recrawl = recrawl
		

		# We're hardcoding the domain and subdomain to avoid accidental 
		# queuing and or crawling of domains we're not interested in. 
		# These fields need to be changed here manually if adding more 
		# domains and subdomains in the future.
		self.kwargs['domain'] = 'Appliances'
		self.kwargs['subdomain'] = 'Refrigeration'

	def _build_kwargs(self, url_obj):
		kwargs = {}
		try:
			kwargs = {
				'merchant': url_obj.merchant,
				'base_url': url_obj.url,
				'url_obj': url_obj
			}
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)
		return kwargs

	def crawl_landing(self):
		'''
		Initiate preliminary crawling to obtain the landing page.
		'''
		while True:
			params = {
				'landing_crawled': self.recrawl,
				 'landing_parsed': False,
				 'valid_url_schema': True,
				 'crawl_success': False,
			}
			url_set = c_models.CorpusLandingURL.objects.filter(**params)
			url_obj_list = [obj for obj in url_set]
			count = len(url_obj_list)
			if count > 0:
				logger.info('About to crawl {} corpus landing pages'.format(count))
				with ThreadPoolExecutor(max_workers=self.THREAD_COUNT) as executor:
					for url_obj in url_obj_list:
						try:
							kwargs = self._build_kwargs(url_obj)
							kwargs['crawl_landing'] = True
							cc = crawler.CorpusCrawler(**kwargs)
							executor.submit(cc.crawl)
						except Exception as e:
							msg = '{}: {}'.format(type(e).__name__, e.args[0])
							logger.exception(msg)
			else:
				msg = 'There are no landing page URLs to crawl'
				logger.info(msg)
				break

	def crawl_corpus(self):
		'''
		Initiate corpus crawling. Keep looping until all URLs have been crawled.

		Looping might be inadvisable if we have malformed URLs that will never 
		be crawled.
		'''
		while True:
			cc = crawler.CorpusCrawler(**{'crawl_corpus': True})
			url_list = cc.get_url_list()
			logger.info('About to crawl {} corpus pages'.format(len(url_list)))
			with ThreadPoolExecutor(max_workers=self.THREAD_COUNT) as executor:
				for url in url_list:
					try:
						executor.submit(cc.crawl, url=url)
					except Exception as e:
						msg = '{}: {}'.format(type(e).__name__, e.args[0])
						logger.exception(msg)
			if len(url_list) == 0:
				logger.info('There are no corpus URLs to crawl')
				break

	def parse_landing(self):
		'''
		Initiate landing page parsing to extract page count and review count. 
		We may also opt to parse out the product taxonomy to verify
		that it's within our target domain and subdomain.
		'''
		try:
			lp = landing_parsrer.LandingPageParser(**self.kwargs)
			lp.parse_landing()
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)

	def parse_corpus(self):
		'''
		Initiate corpus parsing. 

		Corpus parsing is where we get the information we need to build new 
		URLs. These URLs are later queued and crawled by AnalysisCrawler.

		Running any parsing process in a multithreaded environment doesn't 
		affect the time at all; it's both a CPU- and IO-bound operation, which 
		is bad news for Python. In addiion, there are some race conditions where
		we'd be parsing in one thread what's already been parsed in another. There's
		really no imperative to multithread so we won't consider that for any of our 
		internal operations. However, threading works quite well for crawling, which 
		is the most time-consuming process. 
		'''
		
		try:
			cp = corpus_parser.CorpusParser(**self.kwargs)
			cache_count = len(cp.cache_set)
			if cache_count > 0:
				msg = 'About to parse {} corpus cache pages'.format(cache_count)
				logger.info(msg)
				cp.stage_parsing()
			else:
				msg = 'There are no corpus caches to parse for merchant={}'.format(self.merchant)
				logger.info(msg)
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)

	def build_urls(self):
		'''
		Build corpus crawling URLs.

		We run url builder after crawling and parsing the landing pages, 
		which give us all the information we need to build the URLs. Once 
		we have the URLs, we can begin crawling the entire set of product
		result pages.
		'''
		try:
			url_builder.CorpusURLBuilder(**self.kwargs).build_urls()
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)

	def queue_urls(self):
		'''
		Initiate queuing of review URLs, a.k.a. analysis URLs.

		When we call CorpusQueuer, CorpusQueuer calls CrawlQueuer, which 
		computes new review URLs based on page_count or review_count that
		have been parsed after we called parse_corpus().
		'''
		try:
			cq = corpus_queuer.CorpusQueuer(**self.kwargs)
			cq.stage_queuing()
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)

	def crawl_training(self):
		'''
		Initiate review page crawling for training data. Continue looping
		until there are no more URLs to crawl for the given URL parameters.
		If a recrawl is requested, it needs to be done by calling 
		CorpousWorkflow recrawl=True and training=True.
		'''
		self.kwargs['training'] = True
		try:
			while True:
				rc = review_crawler.ReviewCrawler(**self.kwargs)
				url_count = len(rc.url_list)
				msg = 'About to crawl {} review URLs for TRAINING'
				logger.info(msg.format(url_count))
				if url_count > 0:
					rc.async_staging()
				else:
					msg = 'There are no training review URLs to crawl'
					logger.info(msg)
					return
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)



