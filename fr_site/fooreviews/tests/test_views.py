import pytest
from django.test import RequestFactory
from mixer.backend.django import mixer
pytestmark = pytest.mark.django_db # enable db write access


from .. import views
from .. views import * #this needs to be 'from .. import views' once the index view is changed to class view
from .. import models

class TestHomeView:
    def test_anonymous(self):
        request = RequestFactory().get('/')
        response = views.index(request)
        assert response.status_code == 200, 'Should be callable by anyone'

class TestArticleListView:
    def test_get_queryset(self):
        request = RequestFactory().get('/articles')
        response = views.ArticleListView.as_view()(request)
        assert response.status_code == 200, 'Should be callable by anyone'

class TestArticleDetailtView:
    def test_get_context_data(self):
        article_obj = mixer.blend(models.Article)
        assert article_obj.pk == 1, 'Should have an instance.'

        article_obj_slug = article_obj.get_absolute_url()
        article_obj_url = '/articles/' + article_obj_slug
        request = RequestFactory().get(article_obj.get_absolute_url)
        response = views.ArticleDetailView.as_view()(request, slug=article_obj.slug)
        assert response.status_code == 200, 'Should be callable by anyone'
