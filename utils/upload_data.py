"""Data upload utils for Elasticpath."""
import json
import os
import tempfile

import httpx
from slugify import slugify

from elasticpath.api import ElasticpathAPI
from elasticpath.models import Product
from settings import settings


def upload_products_from_file(products_file_name) -> None:
    """Read file with products data and create those products in Elasticpath."""
    with open(products_file_name, 'r') as products_file:
        products_json = json.load(products_file)

    elasticpath_api = ElasticpathAPI(
        client_id=settings.elasticpath_client_id,
        client_secret=settings.elasticpath_client_secret,
    )

    for product_data in products_json:
        product = elasticpath_api.products.create_product(
            name=product_data['name'],
            sku=product_data['name'],
            slug=slugify(product_data['name']),
            manage_stock=False,
            description=product_data['description'],
            price_amount=product_data['price'],
            price_currency='RUB',
            price_includes_tax=True,
            status='live',
            commodity_type='physical',
        )
        add_picture_for_product(product, product_data['product_image']['url'])


def add_picture_for_product(product: Product, picture_url: str) -> None:
    """Upload picture to Elasticpath and assign it as a main image for a product."""
    elasticpath_api = ElasticpathAPI(
        client_id=settings.elasticpath_client_id,
        client_secret=settings.elasticpath_client_secret,
    )
    product_picture = httpx.get(picture_url).content

    picture_file = tempfile.NamedTemporaryFile(delete=False)
    picture_file.write(product_picture)
    picture_file.close()

    elasticpath_file = elasticpath_api.files.create_file(picture_file.name)
    elasticpath_api.products.add_main_image_to_product(elasticpath_file, product)

    os.remove(picture_file.name)
