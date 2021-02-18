"""Models that represent common Elasticpath entities like product, cart, etc."""
from typing import Union


class Product:
    """Represents a product from Elasticpath shop."""

    def __init__(self, product_data: dict):
        self._product_data = product_data

        self.id = self._product_data['id']
        self.name = self._product_data['name']
        self.description = self._product_data['description']

        product_meta = self._product_data['meta']
        self.formatted_price = product_meta['display_price']['with_tax']['formatted']
        self.stock_level = product_meta['stock']['level']
        self.stock_availability = product_meta['stock']['availability']

        main_image = self._product_data['relationships'].get('main_image')
        self.main_image_id = main_image['data']['id'] if main_image is not None else None


class Cart:
    """Represents a cart from Elasticpath shop."""

    def __init__(self, reference: Union[str, int], cart_data: dict):
        self._cart_data = cart_data

        self.reference = reference
        self.id = self._cart_data['id']

        cart_meta = self._cart_data['meta']
        self.formatted_price = cart_meta['display_price']['with_tax']['formatted']


class CartItem:
    """Represents a cart item from Elasticpath shop."""

    def __init__(self, cart_item_data: dict):
        self._cart_item_data = cart_item_data

        self.id = self._cart_item_data['id']
        self.name = self._cart_item_data['name']
        self.product_id = self._cart_item_data['product_id']
        self.quantity = self._cart_item_data['quantity']
        self.description = self._cart_item_data['description']

        cart_item_meta = self._cart_item_data['meta']
        self.formatted_price = cart_item_meta['display_price']['with_tax']['unit']['formatted']


class File:
    """Represents a file from Elasticpath shop."""

    def __init__(self, file_data: dict):
        self._file_data = file_data

        self.id = self._file_data['id']
        self.link = self._file_data['link']['href']


class Flow:
    """Represents a flow from Elasticpath shop."""

    def __init__(self, flow_data: dict):
        self._flow_data = flow_data

        self.id = self._flow_data['id']
        self.name = self._flow_data['name']


class Field:
    """Represents a field from Elasticpath shop."""

    def __init__(self, field_data: dict):
        self._field_data = field_data

        self.id = self._field_data['id']
        self.name = self._field_data['name']
