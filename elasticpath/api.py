"""Wrapper for Elasticpath API."""
import contextlib
import logging
import time
from typing import Callable, List, Optional, Tuple, Union

import httpx

from elasticpath.models import Cart, CartItem, Field, File, Flow, Product

ELASTICPATH_AUTH_URL = 'https://api.moltin.com/oauth/access_token'
ELASTICPATH_API_URL = 'https://api.moltin.com/v2'

logger = logging.getLogger()


class ElasticpathAPI:
    """Wrapper for Elasticpath API."""

    def __init__(self, client_id: str, client_secret: Optional[str] = None) -> None:
        self._session = _APISession(client_id, client_secret)

        self.products = _ProductsAPI(self._session)
        self.carts = _CartsAPI(self._session)
        self.files = _FilesAPI(self._session)
        self.customers = _CustomersAPI(self._session)
        self.flows = _FlowsAPI(self._session)
        self.fields = _FieldsAPI(self._session)


class _APISession:
    """Elasticpath API HTTP connection."""

    def __init__(self, client_id: str, client_secret: Optional[str] = None) -> None:
        self._client = None
        self._expires_at = 0

        self._client_id = client_id
        self._client_secret = client_secret

    @property
    def client(self) -> httpx.Client:
        """Authorize client to work with Elasticpath API. Refresh after expiration."""
        if (self._client is None) or (time.time() >= self._expires_at):
            client, expires_at = self._authorize()
            self._client = client
            self._expires_at = expires_at
        return self._client

    def get(self, *args, **kwargs) -> httpx.Response:
        """Perform HTTP GET request."""
        return self._make_request(self.client.get, *args, **kwargs)

    def post(self, *args, **kwargs) -> httpx.Response:
        """Perform HTTP POST request."""
        return self._make_request(self.client.post, *args, **kwargs)

    def delete(self, *args, **kwargs) -> httpx.Response:
        """Perform HTTP DELETE request."""
        return self._make_request(self.client.delete, *args, **kwargs)

    def _make_request(self, requester: Callable, *args, **kwargs) -> httpx.Response:
        """Perform HTTP request with error handling."""
        response = requester(*args, **kwargs)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            with contextlib.suppress():
                logger.error(response.json())
            raise
        return response

    def _authorize(self) -> Tuple[httpx.Client, int]:
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

        access_token = response.json()['access_token']
        expires_at = response.json()['expires']

        return (
            httpx.Client(headers={'Authorization': f'Bearer {access_token}'}),
            expires_at,
        )


class _ProductsAPI:
    """Wrapper for Elasticpath products resource."""

    def __init__(self, session: _APISession) -> None:
        self._session = session
        self._url = f'{ELASTICPATH_API_URL}/products'

    def get_product(self, product_id: str) -> 'Product':
        """Get product by id."""
        response = self._session.get(f'{self._url}/{product_id}')
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
        response = self._session.post(f'{self._url}', json={'data': product_data})
        product_data = response.json()['data']

        return Product(product_data)

    def get_products(self, *, limit: int = 10, offset: int = 0) -> List['Product']:
        """Get all products from the API using limit/offset pagination."""
        response = self._session.get(
            f'{self._url}',
            params={'page[limit]': limit, 'page[offset]': offset},
        )
        all_products_data = response.json()['data']

        products = []
        for product_data in all_products_data:
            products.append(Product(product_data))
        return products

    def add_file_to_product(self, file: 'File', product: 'Product'):
        """Create relationship between a file and a product."""
        self._session.post(
            f'{self._url}/{product.id}/relationships/files',
            json=[{'type': 'file', 'id': file.id}],
        )

    def add_main_image_to_product(self, file: 'File', product: 'Product'):
        """Create relationship between a file and a product."""
        self._session.post(
            f'{self._url}/{product.id}/relationships/main-image',
            json={'data': {'type': 'main_image', 'id': file.id}},
        )


class _CartsAPI:
    """Wrapper for Elasticpath carts resource."""

    def __init__(self, session: _APISession) -> None:
        self._session = session
        self._url = f'{ELASTICPATH_API_URL}/carts'

    def get_or_create_cart(self, cart_reference: Union[str, int]) -> 'Cart':
        """Get cart by reference, create if it doesn't exist."""
        response = self._session.get(f'{self._url}/{cart_reference}')
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
        self._session.post(
            f'{self._url}/{cart.reference}/items',
            json=product_data,
        )

    def get_cart_items(self, cart: 'Cart') -> List['CartItem']:
        """Get contents of a cart."""
        cart_items_url = f'{self._url}/{cart.reference}/items'
        response = self._session.get(cart_items_url)
        all_cart_items_data = response.json()['data']

        cart_items = []
        for cart_item_data in all_cart_items_data:
            cart_items.append(CartItem(cart_item_data))
        return cart_items

    def remove_cart_item(self, cart: 'Cart', cart_item_id) -> None:
        """Remove item from cart."""
        cart_item_url = f'{self._url}/{cart.reference}/items/{cart_item_id}'
        self._session.delete(cart_item_url)


class _FilesAPI:
    """Wrapper for Elasticpath files resource."""

    def __init__(self, session: _APISession) -> None:
        self._session = session
        self._url = f'{ELASTICPATH_API_URL}/files'

    def get_file(self, file_id: str) -> 'File':
        """Get single file from Elasticpath."""
        response = self._session.get(f'{self._url}/{file_id}')
        file_data = response.json()['data']

        return File(file_data)

    def create_file(self, file_name: str, is_public: bool = True) -> 'File':
        """Create file in Elasticpath."""
        with open(file_name, 'r+b') as file_descriptor:
            response = self._session.post(
                f'{self._url}',
                json={'public': is_public},
                files={'file': file_descriptor},
            )
        file_data = response.json()['data']

        return File(file_data)


class _CustomersAPI:
    """Wrapper for Elasticpath customers resource."""

    def __init__(self, session: _APISession) -> None:
        self._session = session
        self._url = f'{ELASTICPATH_API_URL}/customers'

    def create_customer(self, email: str, name: str = 'Anonymous') -> None:
        """Create customer in ElasticPath shop."""
        customer_data = {
            'data': {
                'type': 'customer',
                'name': name,
                'email': email,
            },
        }
        self._session.post(f'{self._url}', json=customer_data)


class _FlowsAPI:
    """Wrapper for Elasticpath flows resource."""

    def __init__(self, session: _APISession) -> None:
        self._session = session
        self._url = f'{ELASTICPATH_API_URL}/flows'

    def create_flow(self, enabled: bool, description: str, slug: str, name: str) -> Flow:
        """Create flow in ElasticPath shop."""
        flow_data = {
            'data': {
                'type': 'flow',
                'name': name,
                'slug': slug,
                'description': description,
                'enabled': enabled,
            },
        }
        response = self._session.post(f'{self._url}', json=flow_data)

        flow_data = response.json()['data']
        return Flow(flow_data)

    def create_entry(self, flow: Union[str, Flow], fields: dict) -> None:
        """
        Create entry for a flow.

        :param flow: Flow object or a slug for the flow you are requesting an entry for.
        :param fields: Dict with field slug for each field on this flow along
         with the corresponding value for this entry.
        """
        flow_slug = flow.slug if isinstance(flow, Flow) else flow
        entry_data = {
            'data': {
                'type': 'entry',
                **fields,
            },
        }
        self._session.post(f'{self._url}/{flow_slug}/entries', json=entry_data)


class _FieldsAPI:
    """Wrapper for Elasticpath fields resource."""

    def __init__(self, session: _APISession) -> None:
        self._session = session
        self._url = f'{ELASTICPATH_API_URL}/fields'

    def create_field(
            self,
            enabled: bool,
            description: str,
            slug: str,
            name: str,
            field_type: str,
            required: bool,
            flow: Flow,
    ) -> Field:
        """Create field in ElasticPath shop."""
        available_types = ['string', 'integer', 'boolean', 'float', 'relationship', 'date']
        if field_type not in available_types:
            raise ValueError(f'Field type {field_type} must be one of {available_types}')

        field_data = {
            'data': {
                'type': 'field',
                'name': name,
                'slug': slug,
                'description': description,
                'enabled': enabled,
                'field_type': field_type,
                'required': required,
                'relationships': {
                    'flow': {
                        'data': {
                            'type': 'flow',
                            'id': flow.id,
                        },
                    },
                },
            },
        }
        response = self._session.post(f'{self._url}', json=field_data)

        field_data = response.json()['data']
        return Field(field_data)
