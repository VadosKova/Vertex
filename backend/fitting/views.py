from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from avatars.models import Avatar
from catalog.views import visible_products

from .engine import evaluate_product, evaluate_size, recommend_size
from .models import TryOnItem, TryOnSession
from . import serializers as s


MAX_ITEMS_PER_SESSION = 10