import copy
# import crawler.models as c_models
import ml.models as m_models
import fooreviews.article_data.article_formatter as article_formatter
import fooreviews.helper as helper
import fooreviews.models as f_models
import graphing.graphing_data as gdata
from urllib import quote_plus
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

def get_graphing_data(request, frsku=None, article=None):
    slug = request.path.replace('/','')
    graph_data = {}
    try:
        graph_data = gdata.GraphingData(slug, frsku=frsku, article=article).get_data()
    except Exception as e:
        msg = '{}: {}'.format(type(e).__name__, e.args[0])
        logger.exception(msg)
    return graph_data

def get_share_string(article_obj):
    '''
    Return an encoded title string for embedding into social share_string sites.
    '''
    share_string = quote_plus(article_obj.article_title)
    return share_string

def get_related(article_obj):
    '''
    Get related articles for populating the 'Related Reviews' section. 
    Initially, we're just getting the three most recent articles, 
    excluding the one under which this section is found. We'll 
    implement the retrieval of related articles with Elasticsearch's 
    'more like this' feature once we have enough inventory of articles. 

    NB: 'Recent Reviews' and list view use different templates because 
    list view queries Elasticsearch, whereas recent reviews queries postgres. 
    We can query Elasticsearch for everything, but it gets complicated and hard 
    to justify the overhead.
    '''
    params = {'published': True, 'draft': False}
    related_set = f_models.Article.objects.filter(**params).order_by('-created_at')[:4]

    # exclude article_obj
    excluded_obj_list = []
    excluded_obj_list = [obj for obj in related_set if obj.id != article_obj.id]
    if len(excluded_obj_list) == 4:
        excluded_obj_list.pop(-1)
    if excluded_obj_list:
        return excluded_obj_list, True
    return excluded_obj_list, False

def get_image_url(article_obj):

    try:
        full_img_url = helper.full_img_url(article_obj.product.image.url)
    except Exception as e:
        msg = '{}: {}'.format(type(e).__name__, e.args[0])
        logger.exception(msg)
        full_img_url = 'IMAGE_NOT_FOUND'
    return full_img_url

def get_breadcrumb(article_obj):
    return helper.get_breadcrumb(article_obj)

def _get_raw_rev_count(data_obj):
    count = 0
    clf = data_obj.data.get('Classification')
    for clf_type, value in clf.items():
        # sum review count for Duplicate, Legitimate, and Spam
        count += value.get('review_count')
    return count

def _get_aspect_count(data_obj):
    ASPECTS_ANALYZED = 20 # this doesn't change
    count_dict = {
        'aspects_discovered': data_obj.data.get('Aspects Discovered'),
        'aspects_analyzed': ASPECTS_ANALYZED,
    }
    return count_dict


def get_intro_stats(article_obj):
    '''
    Return some analysis figures to display in the introductory section of 
    the article.
    '''
    params = {
        'frsku': article_obj.product.frsku,
    }
    data_obj = m_models.Data.objects.filter(**params)[0]

    # comma-separate count if greater than 999
    schema_review_count = _get_raw_rev_count(data_obj) #int
    review_count = "{:,}".format(schema_review_count) # string
    kwargs = {
        'reviews_analyzed': review_count,
        'schema_review_count': schema_review_count,
    }
    kwargs.update(_get_aspect_count(data_obj))
    return kwargs
    
def _update_context(context, request, article_obj, frsku=None):
    '''
    Update the context dictionary with preformatted data. 
    The functions and classes called here return the data in a dictionary format. 
    We populate the template by accessing the key-value pairs directly so we want
    to maintain the relationships here.
    '''
    # get key specs, pricing, etc
    fa = article_formatter.FormatArticle(article_obj)
    fa.update_article()
    formatted_content = fa.get_formatted_content()
    context.update(formatted_content)

    # get graphing data
    graphing_data = get_graphing_data(request, frsku=frsku, article=article_obj)
    context.update(graphing_data)
    
    
    # get adjusted rating stars
    adjusted_star_rating = fa._get_star_rating(context.get('adjusted_rating'))
    context['adjusted_star_rating'] = adjusted_star_rating

    # get introductory stats
    context.update(get_intro_stats(article_obj))

    return context

def _update_article_obj(article_obj, context):
    '''
    Update article object fields for Elasticsearch aggregation and 
    sorting based on the values computed thus far. Because we're updating 
    the article object after we get a request from views.py, certain 
    html attributes won't be populated until after we save article_obj and 
    Elasticsearch index get updated (this automatically upon saving article_obj). 
    '''

    article_obj.adjusted_rating = context.get('adjusted_rating')
    article_obj.adjusted_star_rating = context.get('adjusted_star_rating')
    article_obj.aspect_count = context.get('aspects_discovered')
    article_obj.review_count = context.get('schema_review_count')
    article_obj.save()

def _cache_context(context, article_obj):
    '''
    Caches article context dictionary to db. 

    The caching doesn't seem to provide any benefit. The main bottleneck
    in the request cycle is related item lookup for 'Most Recent' reviews.
    This should not be an issue once we start using Elasticsearch directly
    instead of Postgres. In addition, site-wide caching once the site is 
    in production should perform it's own serialization and eliminate the 
    need for manual caching. 
    '''
    entry = {
        'article': article_obj,
        'context': context
    }
    f_models.ArticleContextCache.objects.create(**entry)

def _get_cached_context(article_obj):
    lookup = {
        'article__product__frsku': article_obj.product.frsku
    }
    context_set = f_models.ArticleContextCache.objects.filter(**lookup)
    if context_set:
        context = context_set[0].context
        context['article'] = article_obj
        context['related_article_set'] = get_related(article_obj)
def get_article_obj(request):
    '''
    Return a models.Article object.
    '''
    url_tokens = [token for token in request.path.split('/') if token]
    slug = url_tokens[-1]
    params = {
        'slug': slug,
        'download_charts': True,

    }
    article_obj = f_models.Article.objects.filter(**params)[0]
    return article_obj, article_obj.product.frsku

def get_where_to_buy(article_obj):
    '''
    Return a dictionary of product-specific merchant URLs.
    '''
    params = {'article__product__frsku': article_obj.product.frsku}
    merchants = f_models.WhereToBuy.objects.filter(**params)
    where_to_buy = {}
    if merchants.count():
        for m in merchants:
            where_to_buy[m.merchant] = m.url
    return where_to_buy

def get_context(request, article_obj):
    '''
    Return a fully formatted context dictionary to be passed to the 
    article DetailView template.
    '''
    
    context = {}
    load_highcharts_exporting_js = False
    data_page_enabled = False
    frsku = None
    try:
        if not article_obj:
            article_obj, frsku = get_article_obj(request)
            load_highcharts_exporting_js = True
        related_set, related_found = get_related(article_obj)
        if article_obj.download_charts:
            data_page_enabled = True
        context = {
             "article": article_obj,
             "related_article_set": related_set,
             "full_img_url": get_image_url(article_obj),
             'breadcrumb': get_breadcrumb(article_obj),
             "share_string": get_share_string(article_obj),
             'load_highcharts_js': True,
             'load_highcharts_exporting_js': load_highcharts_exporting_js,
             'related_found': related_found,
             'where_to_buy': get_where_to_buy(article_obj),
             'data_page_enabled': data_page_enabled,
        }
        context = _update_context(context, request, article_obj, frsku=frsku)
        if not article_obj.context_upto_date:
            _update_article_obj(article_obj, context)
    except Exception as e:
        msg = '{}: {}'.format(type(e).__name__, e.args[0])
        logger.exception(msg)
    return context


