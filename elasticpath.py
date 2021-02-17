"""
Module to work with Elasticpath API.

Contains wrapper for the API and classes for common entities like product, cart, etc.
"""
import time
from typing import List, Union, Optional, IO

import httpx

ELASTICPATH_AUTH_URL = 'https://api.moltin.com/oauth/access_token'
ELASTICPATH_API_URL = 'https://api.moltin.com/v2'


class ElasticPathAPI:
    """Wrapper for Elasticpath API."""

    def __init__(self, client_id: str, client_secret: Optional[str] = None) -> None:
        self._client = None
        self._expires_at = 0

        self._client_id = client_id
        self._client_secret = client_secret

    @property
    def client(self) -> httpx.Client:
        """Authorize client to work with Elasticpath API. Refresh after expiration."""
        if (self._client is None) or (time.time() >= self._expires_at):
            self._authorize()
        return self._client

    def get_product(self, product_id: str) -> 'Product':
        """Get product by id."""
        response = self.client.get(f'{ELASTICPATH_API_URL}/products/{product_id}')
        response.raise_for_status()

        product_data = response.json()['data']
        return Product(product_data)

    def create_product(
            self,
            name: str,
            slug: str,
            sku: str,
            manage_stock: bool,
            description: str,
            price_amount: int,
            price_currency: str,
            price_includes_tax: bool,
            status: str,
            commodity_type: str,
    ) -> 'Product':
        """
        Create a product.

        Data that needs to be provided described here:
        https://documentation.elasticpath.com/commerce-cloud/docs/api/catalog/products/create-a-product.html
        """
        product_data = {
            'type': 'product',
            'name': name,
            'slug': slug,
            'sku': sku,
            'description': description,
            'manage_stock': manage_stock,
            'price': [
                {
                    'amount': price_amount,
                    'currency': price_currency,
                    'includes_tax': price_includes_tax,
                },
            ],
            'status': status,
            'commodity_type': commodity_type,
        }
        response = self.client.post(f'{ELASTICPATH_API_URL}/products', json={'data': product_data})
        response.raise_for_status()

        product_data = response.json()['data']
        return Product(product_data)

    def get_products(self, *, limit: int = 10, offset: int = 0) -> List['Product']:
        """Get all products from the API using limit/offset pagination."""
        response = self.client.get(
            f'{ELASTICPATH_API_URL}/products?page[limit]={limit}&page[offset]={offset}',
        )
        response.raise_for_status()

        all_products_data = response.json()['data']

        products = []
        for product_data in all_products_data:
            products.append(Product(product_data))
        return products

    def add_file_to_product(self, file: 'File', product: 'Product'):
        """Create relationship between a file and a product."""
        file_data = [{'type': 'file', 'id': file.id}]
        response = self.client.post(
            f'{ELASTICPATH_API_URL}/products/{product.id}/relationships/files',
            json=file_data
        )
        response.raise_for_status()

    def add_main_image_to_product(self, file: 'File', product: 'Product'):
        """Create relationship between a file and a product."""
        file_data = {'data': {'type': 'main_image', 'id': file.id}}
        response = self.client.post(
            f'{ELASTICPATH_API_URL}/products/{product.id}/relationships/main-image',
            json=file_data
        )
        response.raise_for_status()

    def get_or_create_cart(self, cart_reference: Union[str, int]) -> 'Cart':
        """Get cart by reference, create if it doesn't exist."""
        response = self.client.get(f'{ELASTICPATH_API_URL}/carts/{cart_reference}')
        response.raise_for_status()

        cart_data = response.json()['data']
        return Cart(cart_reference, cart_data)

    def add_product_to_cart(self, product: 'Product', cart: 'Cart', quantity: int = 1) -> None:
        """Add one or more items of a product to a cart."""
        product_data = {
            'data': {
                'quantity': quantity,
                'type': 'cart_item',
                'id': product.id,
            },
        }
        response = self.client.post(
            f'{ELASTICPATH_API_URL}/carts/{cart.reference}/items',
            json=product_data,
        )
        response.raise_for_status()

    def get_cart_items(self, cart: 'Cart') -> List['CartItem']:
        """Get contents of a cart."""
        response = self.client.get(f'{ELASTICPATH_API_URL}/carts/{cart.reference}/items')
        response.raise_for_status()

        all_cart_items_data = response.json()['data']

        cart_items = []
        for cart_item_data in all_cart_items_data:
            cart_items.append(CartItem(cart_item_data))
        return cart_items

    def remove_cart_item(self, cart: 'Cart', cart_item_id) -> None:
        """Remove the item from cart."""
        response = self.client.delete(
            f'{ELASTICPATH_API_URL}/carts/{cart.reference}/items/{cart_item_id}',
        )
        response.raise_for_status()

    def get_file(self, file_id: str) -> 'File':
        """Get URL for a file."""
        response = self.client.get(f'{ELASTICPATH_API_URL}/files/{file_id}')
        response.raise_for_status()

        file_data = response.json()['data']
        return File(file_data)

    def create_file(self, file_descriptor: IO, is_public: bool = True) -> 'File':
        """Get URL for a file."""
        response = self.client.post(
            f'{ELASTICPATH_API_URL}/files',
            json={'public': is_public},
            files={'file': file_descriptor},
        )
        response.raise_for_status()

        file_data = response.json()['data']
        return File(file_data)

    def create_customer(self, email: str, name: str = 'Anonymous') -> None:
        """Create customer in ElasticPath shop."""
        customer_data = {
            'data': {
                'type': 'customer',
                'name': name,
                'email': email,
            },
        }
        response = self.client.post(f'{ELASTICPATH_API_URL}/customers', json=customer_data)
        response.raise_for_status()

    def _authorize(self):
        """Authorize at Elasticpath API."""
        if self._client_secret is None:
            auth_data = {'client_id': self._client_id, 'grant_type': 'implicit'}
        else:
            auth_data = {
                'client_id': self._client_id,
                'client_secret': self._client_secret,
                'grant_type': 'client_credentials',
            }
        response = httpx.post(ELASTICPATH_AUTH_URL, data=auth_data)
        response.raise_for_status()

        auth_response_data = response.json()
        access_token = auth_response_data['access_token']
        expires_at = auth_response_data['expires']

        headers = {'Authorization': f'Bearer {access_token}'}
        self._client = httpx.Client(headers=headers)
        self._expires_at = expires_at


class Product:
    """Represents a product from Elasticpath shop."""

    def __init__(self, product_data: dict):
        self._product_data = product_data

        self.id = self._product_data['id']
        self.name = self._product_data['name']
        self.description = self._product_data['description']

        self.formatted_price = self._product_data['meta']['display_price']['with_tax']['formatted']
        self.stock_level = self._product_data['meta']['stock']['level']
        self.stock_availability = self._product_data['meta']['stock']['availability']

        if 'main_image' in self._product_data['relationships']:
            self.main_image_id = self._product_data['relationships']['main_image']['data']['id']
        else:
            self.main_image_id = None


class Cart:
    """Represents a cart from Elasticpath shop."""

    def __init__(self, reference: Union[str, int], cart_data: dict):
        self._cart_data = cart_data

        self.reference = reference
        self.id = self._cart_data['id']
        self.formatted_price = self._cart_data['meta']['display_price']['with_tax']['formatted']


class CartItem:
    """Represents a cart item from Elasticpath shop."""

    def __init__(self, cart_item_data: dict):
        self._cart_item_data = cart_item_data

        self.id = self._cart_item_data['id']
        self.name = self._cart_item_data['name']
        self.product_id = self._cart_item_data['product_id']
        self.quantity = self._cart_item_data['quantity']
        self.description = self._cart_item_data['description']

        self.formatted_price = (
            self._cart_item_data['meta']['display_price']['with_tax']['unit']['formatted']
        )


class File:
    """Represents a file from Elasticpath shop."""

    def __init__(self, file_data: dict):
        self._file_data = file_data

        self.id = self._file_data['id']
        self.link = self._file_data['link']['href']
