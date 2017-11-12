import unicodedata, re
from django.utils.safestring import SafeText
import csv
from stop_words import get_stop_words 

def slug_exists(base_slug, queryset):
    '''
    Check if the  slug exists in the database. If it does, increment 
    the count of the number of objects with that slug and return the value.
    Otherwise, return False.
    '''
    filtered_set = queryset.filter(base_slug=base_slug)
    count = 0
    count_list = []
    if filtered_set:
        for obj in filtered_set:
            if obj.slug != None:
                if obj.slug == base_slug:
                    count = 1
                    count_list.append(count)
                else:
                    # assume we have a number appended  to the end of the slug
                    slug_tokens = (obj.slug).split('-')
                    count = int(slug_tokens[-1])
                    count_list.append(count)
    if count_list:
        count = max(count_list) + 1     
    return count

def unique_slugify(base_slug, Model):
    '''
    Return a unique slug by incrementing the number of base_slug objects already in the db
    and appending that number to the slug. 
    '''
    # Product = 
    queryset_dict = {}
    queryset = Model.objects.filter(base_slug=base_slug).\
                            prefetch_related()
    # queryset_dict['Slug'] = models.Slug.objects.filter(base_slug=base_slug).\
    #                         prefetch_related()
    unique_slug = base_slug
    # queryset = queryset_dict[model_name]
    incremented_count = slug_exists(base_slug, queryset)
  
    if incremented_count:
        unique_slug = base_slug + '-' + str(incremented_count) 
    return unique_slug

def slugify(string):    
    '''
    Given a string, remove all non-alphabetical characters and stop words
    as defined in stop_words; replace spaces with hyphens and 
    convert the slug to a SafeText string format 
    '''
    # TODO: do logging here
    stop_words = get_stop_words('english')
    string = string.replace("'", '') #remove apostrophes
    slug = string.encode('utf-8')
    slug = unicodedata.normalize("NFKD",unicode(string)).encode("ascii", "ignore")
    slug = re.sub(r"[^\w]", " ", slug)
    slug = "-".join([word for word in slug.split() if word not in stop_words])
    slug = slug.lower().strip().split()
    safe_slug = SafeText(slug[0])
    return safe_slug


def get_choices(choice_for=None):
    '''
    Return a tuple of choices.

    We've hard-coded the choices here for now. Later on we might want to 
    store them in a db table. We could consolidate merchant choices into the 
    merchant table. 
    '''
    # crawl status
    UNCRAWLED = 0
    CRAWLED = 1
    FAILED = 2

    
    # merchant type
    CRAWL = 'CRAWL'
    ADVERTISE = 'ADVERTISE'

    # CSS Selector types
    # detail page
    PAGE_COUNT = 'page_count'
    REVIEW_COUNT = 'review_count'
    RATING_VALUE = 'avg_rating'
    SOURCE_TITLE = 'source_title'
    SOURCE_IMAGE = 'source_image'
    PRICE = 'price'
    SPECS = 'specs'

    # review page
    USER_NAME  = 'user_name'
    REVIEW_TITLE = 'review_title'
    REVIEW_BODY = 'review_body'
    REVIEW_DATE = 'review_date'
    REVIEW_ID = 'review_id'
    LOCALITY = 'locality'
    USER_RATING = 'user_rating'
    VERIFIED_PURCHASE = 'verified_purchase'
    RECOMMEND_TO_FRIEND = 'recommend_to_friend'
    HELPFUL_COUNT = 'helpful_count'
    UNHELPFUL_COUNT = 'unhelpful_count'
    MEMBERSHIP = 'membership'


    STATUS = (
        (UNCRAWLED, 0),
        (CRAWLED, 1),
        (FAILED, 2)
    )

    MERCHANT_TYPE = (
            (CRAWL, 'CRAWL'),
            (ADVERTISE, 'ADVERTISE')
        )
    SELECTOR_TYPE = (
        (PAGE_COUNT, 'page_count'),
        (REVIEW_COUNT, 'review_count'),
        (RATING_VALUE, 'avg_rating'),
        (SOURCE_TITLE, 'source_title'),
        (SOURCE_IMAGE,  'source_image'),
        (PRICE, 'price'),
        (SPECS, 'specs'),
        (USER_NAME, 'user_name'),
        (REVIEW_TITLE, 'review_title'),
        (REVIEW_BODY, 'review_body'),
        (REVIEW_DATE, 'review_date'),
        (REVIEW_ID, 'review_id'),
        (LOCALITY, 'locality'),
        (USER_RATING, 'user_rating'),
        (VERIFIED_PURCHASE, 'verified_purchase'),
        (RECOMMEND_TO_FRIEND, 'recommend_to_friend'),
        (HELPFUL_COUNT, 'helpful_count'),
        (UNHELPFUL_COUNT, 'unhelpful_count'),
        (MEMBERSHIP, 'membership'),
    )

    if choice_for == 'STATUS':
        return STATUS
    elif choice_for == 'SELECTOR_TYPE':
        return SELECTOR_TYPE
    elif choice_for == 'MERCHANT_TYPE':
        return MERCHANT_TYPE

def make_directory(logger, root_path):
    import os
    if not os.path.exists(root_path):
        os.makedirs(root_path)
        msg = 'Created new directory: {}'.format(root_path)
    else:
        msg = 'Directory {} already exists'.format(root_path)
    logger.info(msg)