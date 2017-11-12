from .. import helper
import pytest
from .. import models
import random, decimal
from mixer.backend.django import mixer
from django.template.defaultfilters import slugify
pytestmark = pytest.mark.django_db # enable db write access


class TestHelperFunctions:
    def test_get_list(self):
        some_string = "This land is your land \n \
            This land is my land \n \
            From California \n \
            To the Redwood Forest... "
        string_list = helper.get_list(some_string)
        assert len(string_list) == 4, 'Should return a list of 4 elements.'


    def test_match_price_logo(self):
        ''' Create 99 price and merchant objects so that their respective
        Queryset can be passed to helper.match_price_logo(). '''
        i = 0
        while i < 99:
            '''The merchant and price object references are lost  with every
            iteration (since we're not saving them to any list or dictionary
            object global to the while loop) but are retrieved later as a
            queryset from the db. '''
            merchant_obj = mixer.blend(models.Merchant)
            price_obj = mixer.blend(models.Price)
            assert merchant_obj.pk == i + 1, 'Should have an instance.'
            assert price_obj.pk == i + 1, 'Should have an instance.'
            i += 1

        merchant_set = models.Merchant.objects.all().prefetch_related()
        price_set = models.Price.objects.all().prefetch_related()

        '''The function arguments are given in the wrong order. This should
        raise an exception. '''
        try:
            helper.match_price_logo(merchant_set, price_set)
        except Exception:
            assert True
            helper.match_price_logo(price_set, merchant_set)


    def test_price_total(self):
        ''' Create 99 price objects so that their respective
        Queryset can be passed to helper.price_total(). The helper
        funciton doesn't return anything. We just want to make sure that the
        database is properly updated by the function. '''
        i = 0
        total_list = []
        while i < 99:
            '''The price object references are lost  with every
            iteration (since we're not saving them to any list or dictionary
            object global to the while loop) but are retrieved later as a
            queryset from the db. '''
            # Note that we're not filling the price field with a random value;
            # mixer.blend() does that for us.
            tax = decimal.Decimal(random.randrange(10000))/100
            shipping = decimal.Decimal(random.randrange(10000))/100
            price_obj = mixer.blend(models.Price, tax=tax, shipping=shipping)
            total = price_obj.price + tax + shipping
            total_list.append(total)
            assert price_obj.pk == i + 1, 'Should have an instance.'
            i += 1
        price_set = models.Price.objects.all().prefetch_related()
        helper.price_total(price_set)

        ''' Now that the database has been updated, assert that the total price
        for every price object is what it should be. '''
        i = 0
        for price_obj in price_set:
            assert price_obj.total == total_list[i], 'Total price values should match'
            i += 1


    # def test_social_share_link(self):
    #     # Base URLs
    #     fr_base_url = "https://www.fooreviews.com/"
    #     fb_base_url = "https://www.facebook.com/sharer/sharer.php?u="
    #
    #
    #     title = "My fellow Americans, it is in the character of very few men"
    #     slug = slugify(title)
    #     canonical_url = domain + slug
    #     fb_full_url = fb_parent + canonical_url
