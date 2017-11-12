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
    queryset_dict = {}
    queryset = Model.objects.filter(base_slug=base_slug).\
                            prefetch_related()
    unique_slug = base_slug
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

def make_directory(logger, root_path):
    import os
    try:
        if not os.path.exists(root_path):
            os.makedirs(root_path)
            msg = 'Created new directory: {}'.format(root_path)
        else:
            msg = 'Directory {} already exists'.format(root_path)
        logger.info(msg)
    except Exception as e:
        msg = '{}: {}'.format(type(e).__name__, e.args[0])
        logger.exception(msg)