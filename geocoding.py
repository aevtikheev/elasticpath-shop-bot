"""Module to work with geocoding-related stuff."""
import httpx
from typing import Tuple

from settings import settings

YANDEX_GEOCODER_API_URL = 'https://geocode-maps.yandex.ru/1.x'


class UnknownAddressError(Exception):
    """Raised when address is not recognized."""


def fetch_coordinates(address: str) -> Tuple[float, float]:
    """Get latitude and longitude of a place by address."""
    response = httpx.get(
        YANDEX_GEOCODER_API_URL,
        params={'geocode': address, 'apikey': settings.yandex_geocoder_api_key, 'format': 'json'},
    )
    response.raise_for_status()

    found_places = response.json()['response']['GeoObjectCollection']['featureMember']
    if not found_places:
        raise UnknownAddressError
    most_relevant = found_places[0]
    return most_relevant['GeoObject']['Point']['pos'].split(' ')
