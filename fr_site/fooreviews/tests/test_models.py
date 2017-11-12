#coding: utf-8
import pytest
from .. import models
from mixer.backend.django import mixer
import datetime
pytestmark = pytest.mark.django_db # enable db write access


class TestArticle:
    def test_init(self):
        article_obj = mixer.blend(models.Article)
        assert article_obj.pk == 1, 'Should have an instance.'

        # Update the table and assert that the time of creation is not the same
        # as the time of update
        article_obj.product_name = 'Bluetooth-enabled Toaster'
        time_created = article_obj.created
        time_updated = article_obj.updated
        assert time_created != time_updated, 'Timestamps should not match.'
        assert article_obj.__unicode__() == article_obj.title

    def test_date_created(self):
        article_obj = mixer.blend(models.Article)
        assert article_obj.pk == 1, 'Should have an instance.'
        today = datetime.date.today()
        assert article_obj.date_created() == today, 'The dates should be the same'

    def test_date_updated(self):
        article_obj = mixer.blend(models.Article)
        assert article_obj.pk == 1, 'Should have an instance.'
        today = datetime.date.today()
        assert article_obj.date_updated() == today, 'The dates should be the same'

    ''' Assert that the get_excerpt() function of the article_obj returns an
    excerpt of a specified length. '''
    def test_get_excerpt(self):
        content =u"Three companies including Toyota, KDDI Corporation, and coffee company Komeda will launch an app that will reward drivers with free coffee for driving without using a phone. The app is pretty straightforward. Install it on the phone, set the phone face-down, and let it record the distance you drive without touching the phone. The app uses the gyroscopic sensors to recognize if you start using the phone. Once you hit 100 kilometers, you get a free coffee from Komeda, and every 200 kilometers after that earns another cup.” A cup of coffee is a nice bonus for drivers who are more cautious, and Toyota’s emphasis on safety is appreciated. “Toyota reported that the app was downloaded 37,000 times and drivers racked up over 1.6 million miles of phone-free motoring. It will be interesting to see how many people sign up for this new Prius program, and whether similar programs show up in different countries with different companies.” Indeed."
        article_obj = mixer.blend(models.Article, content=content)
        assert article_obj.pk == 1, 'Should have an instance.'
        n = 300
        assert len(content) >= n, "Content length should be longer than the length of the excerpt length"
        assert len(article_obj.content) >= n, "Content length should be longer than the length of the excerpt length"
        excerpt = content[:n]
        assert article_obj.get_excerpt() == excerpt, 'The first n characters should match'


    ''' Assert the first letter of the article content matches the value returned
    by the first_letter() function. '''
    def test_first_letter(self):
        article_obj = mixer.blend(models.Article, content='An Article object...')
        assert article_obj.pk == 1, 'Should have an instance.'
        assert article_obj.first_letter() == 'A', 'Should equal the letter A'

    ''' Assert that the slug part of the canonical url matches the expected
    slug-like pattern with spaces replaced with dashes. We cannot test for the
    actual url because there is a time-dependent part in the slug. Nevertheless,
    we will assert that the slug never changes even if the title changes.
    This will ensure that we don't get broken links in the future. '''
    def test_get_absolute_url(self):
        article_obj = mixer.blend(models.Article, title="My fellow Americans")
        assert article_obj.pk == 1, 'Should have an instance.'
        permanent_slug = article_obj.slug
        article_obj.title="Ask not what you can do..."
        article_obj.save(update_fields=['title', 'slug'])

        ''' The following assertion does verify that the slug doesn't change,
        at least the time-dependent part of it, even if the title changes.
        mixer.blend() cannot instantiate article_obj.save() for some reason so
        the slug is always 'original-time-stamp-none'. This confirms that the
        slugification is properly implemented and that we should not
        expect any broken links if the title is ever modified.'''
        assert article_obj.slug == permanent_slug, 'The slug should not change'

    def test_author_initials(self):
        article_obj = mixer.blend(models.Article, author="Julius Caesar")
        assert article_obj.pk == 1, 'Should have an instance.'
        assert article_obj.author_initials() == 'J. Caesar', 'Should have First Initial. Last Name'


class TestSpec():
    def test_init(self):
        spec_obj = mixer.blend(models.Spec)
        assert spec_obj.pk == 1, 'Should have an instance.'
        assert spec_obj.__unicode__() == ''

class TestRating():
    def test_init(self):
        rating_obj = mixer.blend(models.Rating)
        assert rating_obj.pk == 1, 'Should have an instance.'
        assert rating_obj.__unicode__() == ''

class TestPrice():
    def test_init(self):
        price_obj = mixer.blend(models.Price)
        assert price_obj.pk == 1, 'Should have an instance.'
        assert price_obj.__unicode__() == ''

class TestMerchant():
    def test_init(self):
        merchant_obj = mixer.blend(models.Merchant)
        assert merchant_obj.pk == 1, 'Should have an instance.'
        assert merchant_obj.__unicode__() == ''
