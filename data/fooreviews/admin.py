from django.contrib import admin
from django import forms
import models
from mptt.admin import MPTTModelAdmin


class MerchantAdmin(admin.ModelAdmin):
    list_display = ('name', 'crawl', 'advertise')

class ProductRawInlineAdmin(admin.StackedInline):
    model = models.ProductRaw
    extra = 0
    exclude = ['title', 'image_url', 'rating', #'review_count', 'page_count', \
                'detail_page', 'specs_page','source_product_id', 'specs_raw',\
                'updated', 'update_queue', 'updated_at', #'detail_crawled',\
                #'detail_parsed', 'review_urls_queued', 'review_urls_crawled',\
                #'reviews_parsed','reviews_analyzed', 'article_published'
                ]
    readonly_fields = ('canonical_url', 'image_url', 'queued_urls')

#Display models area in the Admin panel with the specified columns
class ProductAdmin(admin.ModelAdmin):
    '''
    Maps to models.Product  and inlines ProductRaw. Allows for the initial 
    addition of products to the db and selection of required fields. 
    '''
    # TODO: excluded list should include all crawling and parsing-related fields
    list_display = ['temp_title', 'product_taxonomy', 'frsku','workflow_status']
    inlines = [ProductRawInlineAdmin, ]
    # exclude = ['detail_crawled', 'detail_parsed', 'review_urls_queued',
    #             'review_urls_crawled', 'reviews_parsed', 
    #             'reviews_analyzed', 'article_published']
    exclude = ['created_at', 'updated_at','predicted_topics_name',
                ]
    readonly_fields = ['frsku',]



   
# Register the models
admin.site.register(models.Merchant, MerchantAdmin)
admin.site.register(models.Product, ProductAdmin)

