# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.utils import timezone
from mptt.models import TreeForeignKey 

# Create your models here.
class Product(models.Model):
    '''
    Stores everything having to do with a product. Products are added in the front
    end and all appropriate fields are populated in the backend. Populated fields 
    that are required by Elasticsearch are also passed to the search index automatically
    by models.Article.
    '''
    HELP_TEXT_NAME = ''' 
                    The name of the product is the official title of the article.<br/>
                    It is permanently slugified and cannot be changed since it <br/>
                    becomes part of the canonical url of this product. Make <br/>
                    it concise and SEO-friendly.  
                    '''
    HELP_TEXT_SPECS = '''Separate key specs with a semicolon (;). Max 8 specs.'''
   

    temp_title = models.CharField(max_length=60, blank=False, null=True)
    product_name = models.CharField(max_length=60, blank=True, null=True, unique=True,
             help_text=HELP_TEXT_NAME) # ES indexable
    image = models.ImageField(blank=True, null=True)
    image_alt_tag = models.CharField(max_length=256, blank=True, null=True) # ES indexable, snowball

    product_taxonomy = TreeForeignKey('taxonomy.ProductTaxonomy', null=True) # ES indexable, snowball
    product_domain = models.ForeignKey('ml.TrainingDomain', null=True) # ES indexable, snowball
    base_slug = models.SlugField(max_length=256, blank=True, null=True, editable=False)
    slug = models.SlugField(max_length=256, blank=True, null=True, unique=True, editable=False) # ES indexable, snowball

    key_specs = models.TextField(blank=True, null=True, help_text=HELP_TEXT_SPECS) # ES indexable, snowball
    frsku = models.CharField(max_length=32, blank=True, null=True)
    model_num = models.CharField(max_length=256, blank=False, null=True) # ES indexable, Keyword

    # TODO: these are only test fields for faceting and filtering  
    brand = models.CharField(max_length=256, blank=True, null=True) # ES indexable, snowball
   

    # Workflow status fields
    detail_crawled = models.BooleanField(default=False)
    detail_parsed = models.BooleanField(default=False)
    review_urls_queued = models.BooleanField(default=False)
    review_urls_crawled = models.BooleanField(default=False)
    reviews_parsed = models.BooleanField(default=False)
    reviews_analyzed = models.BooleanField(default=False)
    article_published = models.BooleanField(default=False)

    # ML fields
    predicted_topics_name = models.CharField(max_length=1024, blank=True, null=True)

    # Timestamp
    created_at = models.DateTimeField(default=timezone.now) # remove default and set it to auto_now_add=True if we're starting with an emptyr models.Product table
    updated_at = models.DateTimeField(auto_now=True)

    # Data Transfer Status 
    data_dumped = models.BooleanField(default=False)

    def __unicode__(self):
        string = self.product_name
        if not self.product_name:
            string = self.temp_title
        return '%s' % (string)

    def workflow_status(self):
        '''
        DC = Detail crawled
        DP = Detail parsed
        RQ = Review URLs queued
        RC = Review URLs crawled 
        RP = Reviews parsed
        ML = Machine learning: reviews analyzed 
        AP = Article published
        '''
        status = 'DC={} DP={} RQ={} RC={} RP={} ML={} AP={}'
        status = status.format(\
                self.detail_crawled,\
                self.detail_parsed,\
                self.review_urls_queued,\
                self.review_urls_crawled,\
                self.reviews_parsed,\
                self.reviews_analyzed,
                self.article_published\
                )
        return status

class Merchant(models.Model):
    '''
    Stores the names of the merchants used for crawling and or advertising.
    '''
    name = models.CharField(max_length=256, blank=True, null=True)
    crawl = models.BooleanField(default=False)
    advertise = models.BooleanField(default=False)

     # Data Transfer Status 
    data_dumped = models.BooleanField(default=False)
    
    def __unicode__(self):
        return '%s' % (self.name)

class ProductRaw(models.Model):
    '''
    Stores consolidated data from the product detail page of various merchants. 
    The raw class stores data that is mainly used in crawling. 

    '''
    HELP_TEXT_RAW_URL = '''URL for Sears.com must conform to the following '''
    HELP_TEXT_RAW_URL += 'format:<br/>http://www.sears.com/kenmore-24inch-'''
    HELP_TEXT_RAW_URL += '''built-in-dishwasher-w-stainless-steel/'''
    HELP_TEXT_RAW_URL += '''p-02213693000P <br/>'''

    product = models.ForeignKey(Product, blank=True, null=True)
    merchant = models.ForeignKey(Merchant, blank=False, null=True)
    title = models.CharField(max_length=256, blank=False, null=True)
    raw_url = models.CharField(max_length=256, blank=True, null=True, help_text=HELP_TEXT_RAW_URL)
    canonical_url = models.CharField(max_length=256, blank=True, null=True)
    image_url = models.CharField(max_length=256, blank=True, null=True)
    review_count = models.IntegerField(default=0, blank=True, null=True)
    page_count = models.IntegerField(default=0, blank=True, null=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=0.0)
    source_product_id = models.CharField(max_length=256, blank=True, null=True)
    specs_raw = JSONField(blank=True, null=True)
    detail_page = models.TextField(blank=True, null=True)
    specs_page = models.TextField(blank=True, null=True) # Best Buy only

    queued_urls = models.TextField(blank=True, null=True)
    update_queue = models.BooleanField(default=False)
    created_at  = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now)

    # Workflow status fields
    detail_crawled = models.BooleanField(default=False)
    detail_parsed = models.BooleanField(default=False)
    review_urls_queued = models.BooleanField(default=False)
    review_urls_crawled = models.BooleanField(default=False)
    reviews_parsed = models.BooleanField(default=False)

    # Data Transfer Status 
    data_dumped = models.BooleanField(default=False)

    def __unicode__(self):
        string = self.merchant
        if self.product:
            string = '{}: {}'.format(self.product, self.merchant)
        return '%s' % (string) 