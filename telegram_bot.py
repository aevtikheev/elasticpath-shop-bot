"""Telegram bot for Elasticpath shop."""
import json
from typing import Callable, List

from geopy.distance import distance
from redis import Redis
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, Update
from telegram.ext import CallbackContext, Filters, Updater
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from elasticpath.api import ElasticpathAPI
from elasticpath.models import Entry
from geocoding import UnknownAddressError, fetch_coordinates
from settings import settings

START_STATE = 'start state'
PRODUCT_LIST_STATE = 'product list state'
PRODUCT_DESCRIPTION_STATE = 'product description state'
CART_STATE = 'cart state'
WAIT_EMAIL_STATE = 'wait for email state'
WAIT_LOCATION_STATE = 'wait for location state'

PRODUCT_LIST_CALLBACK_DATA = 'product list callback'
SHOW_CART_CALLBACK_DATA = 'show cart callback'
CHECKOUT_CALLBACK_DATA = 'order callback'
NEXT_PAGE_CALLBACK_DATA = 'next page'
PREVIOUS_PAGE_CALLBACK_DATA = 'previous page'

PRODUCT_LIST_PAGE = 'page'
PRODUCT_LIST_PAGE_SIZE = 8
AVAILABLE_PRODUCT_AMOUNTS = (1, )


class ElasticpathShopBot:
    """Telegram bot for Elasticpath shop."""

    def __init__(self, elasticpath_api: ElasticpathAPI, users_db: Redis, shop_flow: str) -> None:
        self.elasticpath_api = elasticpath_api
        self.users_db = users_db
        self.shop_flow = shop_flow

        self._state_functions = {
            START_STATE: self.handle_start_state,
            PRODUCT_LIST_STATE: self.handle_product_list_state,
            PRODUCT_DESCRIPTION_STATE: self.handle_product_description_state,
            CART_STATE: self.handle_cart_state,
            WAIT_LOCATION_STATE: self.handle_location_state,
        }

    def handle_users_reply(self, update: Update, context: CallbackContext):
        """All-in-one handler. Get current state from the DB and execute specific handler."""
        if update.message:
            user_reply = update.message.text
            chat_id = update.message.chat_id
        elif update.callback_query:
            user_reply = update.callback_query.data
            chat_id = update.callback_query.message.chat_id
        else:
            return
        if user_reply == '/start':
            user_state = START_STATE
        else:
            state_in_db = self.users_db.get(chat_id)
            user_state = START_STATE if state_in_db is None else state_in_db.decode('utf-8')

        state_handler = self._state_functions[user_state]
        next_state = state_handler(update, context)
        self.users_db.set(chat_id, next_state)

    def handle_start_state(self, update: Update, context: CallbackContext) -> str:
        """Show available products."""
        context.user_data[PRODUCT_LIST_PAGE] = 0
        self.show_product_list(update, context)
        return PRODUCT_LIST_STATE

    def handle_product_list_state(self, update: Update, context: CallbackContext) -> str:
        """Move between product list pages or show the description for a chosen product."""
        callback_data = update.callback_query.data

        if callback_data == NEXT_PAGE_CALLBACK_DATA:
            context.user_data[PRODUCT_LIST_PAGE] += 1
            self.show_product_list(update, context)
            return PRODUCT_LIST_STATE
        elif callback_data == PREVIOUS_PAGE_CALLBACK_DATA:
            context.user_data[PRODUCT_LIST_PAGE] -= 1
            self.show_product_list(update, context)
            return PRODUCT_LIST_STATE

        # callback_data is a product ID otherwise
        self.show_product_description(update=update, context=context, product_id=callback_data)
        return PRODUCT_DESCRIPTION_STATE

    def handle_product_description_state(self, update: Update, context: CallbackContext) -> str:
        """Move back to product list, show cart or add the product to a cart."""
        callback_data = update.callback_query.data

        if callback_data == PRODUCT_LIST_CALLBACK_DATA:
            self.show_product_list(update, context)
            return PRODUCT_LIST_STATE
        elif callback_data == SHOW_CART_CALLBACK_DATA:
            self.show_cart(update, context)
            return CART_STATE

        # callback_data is a JSON containing product ID and amount
        product_id, amount = deserialize_product_id_and_amount(callback_data)
        cart = self.elasticpath_api.carts.get_or_create_cart(
            update.callback_query.message.chat_id,
        )
        self.elasticpath_api.carts.add_product_to_cart(
            product=self.elasticpath_api.products.get_product(product_id),
            cart=cart,
            quantity=amount,
        )
        update.callback_query.answer('Added')
        self.show_product_description(update=update, context=context, product_id=product_id)
        return PRODUCT_DESCRIPTION_STATE

    def handle_cart_state(self, update: Update, context: CallbackContext) -> str:
        """Return back to product list, change the cart items or ask the location of the user."""
        callback_data = update.callback_query.data

        if callback_data == PRODUCT_LIST_CALLBACK_DATA:
            self.show_product_list(update, context)
            return PRODUCT_LIST_STATE
        elif callback_data == CHECKOUT_CALLBACK_DATA:
            update.callback_query.message.reply_text('Please provide you location or address.')
            return WAIT_LOCATION_STATE

        # callback_data is an item ID
        cart = self.elasticpath_api.carts.get_or_create_cart(
            update.callback_query.message.chat_id,
        )
        cart_item_id = callback_data
        self.elasticpath_api.carts.remove_cart_item(cart, cart_item_id)
        self.show_cart(update, context)
        return CART_STATE

    def handle_location_state(self, update: Update, context: CallbackContext) -> str:
        """Retrieve user's location, show delivery options."""
        if update.message.location is None:
            try:
                user_longitude, user_latitude = fetch_coordinates(update.message.text)
            except UnknownAddressError:
                update.message.reply_text('Location is not recognized. Please try again.')
                return WAIT_LOCATION_STATE
        else:
            location = update.message.location
            user_longitude, user_latitude = location.longitude, location.latitude

        shop_distance = shop_distance_calculator(user_longitude, user_latitude)
        nearest_shop = min(
            self.elasticpath_api.flows.get_all_entries(self.shop_flow),
            key=shop_distance,
        )
        self.show_delivery_options(
            update=update,
            context=context,
            nearest_shop=nearest_shop,
            shop_distance=shop_distance(nearest_shop),
        )

        return START_STATE

    def show_delivery_options(
            self,
            update: Update,
            context: CallbackContext,
            nearest_shop: Entry,
            shop_distance: int,
    ) -> None:
        """Calculate and display delivery price."""
        if shop_distance < 500:
            update.message.reply_text(
                f'Delivery is free! '
                f'Also you can get your order at {nearest_shop.fields["Address"]}. '
                f'It is only {shop_distance} meters away from you.',
            )
        elif shop_distance < 5000:
            update.message.reply_text('Delivery price is 100 rubles.')
        elif shop_distance < 20_000:
            update.message.reply_text('Delivery price is 300 rubles.')
        else:
            update.message.reply_text('Sorry, you are too far away from the nearest shop :(.')

    def show_product_list(self, update: Update, context: CallbackContext) -> None:
        """Display product list with navigation buttons."""
        if update.callback_query is not None:
            # delete the previous product list page
            update.callback_query.delete_message()

        menu_text = '*Please select a product:*'
        buttons = []
        products_to_display = self.elasticpath_api.products.get_products(
            limit=PRODUCT_LIST_PAGE_SIZE,
            offset=PRODUCT_LIST_PAGE_SIZE * context.user_data['page'],
        )
        for product in products_to_display:
            buttons.append([InlineKeyboardButton(product.name, callback_data=product.id)])
        buttons.append(self.navigation_buttons(update, context))

        if update.message:
            update.message.reply_text(
                text=menu_text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            update.callback_query.answer()
            update.callback_query.message.reply_text(
                text=menu_text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.MARKDOWN,
            )

    def navigation_buttons(
            self, update: Update, context: CallbackContext,
    ) -> List[InlineKeyboardButton]:
        """Show navigation buttons for product list."""
        current_page = context.user_data['page']

        navigation_buttons = []
        if current_page > 0:
            navigation_buttons.append(
                InlineKeyboardButton('<<<', callback_data=PREVIOUS_PAGE_CALLBACK_DATA),
            )
        next_page_products_amount = len(
            self.elasticpath_api.products.get_products(
                limit=PRODUCT_LIST_PAGE_SIZE,
                offset=PRODUCT_LIST_PAGE_SIZE * (current_page + 1),
            ),
        )
        if next_page_products_amount > 0:
            navigation_buttons.append(
                InlineKeyboardButton('>>>', callback_data=NEXT_PAGE_CALLBACK_DATA),
            )

        return navigation_buttons

    def show_product_description(
            self,
            update: Update,
            context: CallbackContext,
            product_id: str,
    ) -> None:
        """Display product description with checkout and menu buttons."""
        update.callback_query.answer()

        product = self.elasticpath_api.products.get_product(product_id)
        cart = self.elasticpath_api.carts.get_or_create_cart(update.callback_query.message.chat_id)
        amount_in_cart = self.elasticpath_api.carts.amount_of_product_in_cart(product.id, cart)

        product_description = (
            f'*{product.name}*\n\n'
            f'*Price*: {product.formatted_price}\n'
            f'*Availability*: {product.stock_level} {product.stock_availability}\n'
            f'*In cart*: {amount_in_cart}\n\n'
            f'{product.description}\n'
        )
        add_amount_buttons = []
        for amount in AVAILABLE_PRODUCT_AMOUNTS:
            add_amount_buttons.append(
                InlineKeyboardButton(
                    text=f'Add {amount}',
                    callback_data=serialize_product_id_and_amount(
                        product_id=product.id,
                        amount=amount,
                    ),
                ),
            )
        buttons = [
            add_amount_buttons,
            [InlineKeyboardButton(text='Back to menu', callback_data=PRODUCT_LIST_CALLBACK_DATA)],
            [InlineKeyboardButton(text='Show cart', callback_data=SHOW_CART_CALLBACK_DATA)],
        ]

        update.callback_query.message.reply_photo(
            photo=self.elasticpath_api.files.get_file(product.main_image_id).link,
            caption=product_description,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN,
        )
        update.callback_query.delete_message()

    def show_cart(self, update: Update, context: CallbackContext) -> None:
        """Show cart content with order and menu buttons."""
        update.callback_query.answer()

        buttons = []
        message_text = '*Items in cart*:\n'
        cart = self.elasticpath_api.carts.get_or_create_cart(
            update.callback_query.message.chat_id,
        )
        for cart_item in self.elasticpath_api.carts.get_cart_items(cart):
            message_text += (
                f'*{cart_item.name}*\n'
                f'*Price per unit*: {cart_item.formatted_price}\n'
                f'*Quantity*: {cart_item.quantity}\n'
                f'{cart_item.description}\n\n'
            )
            buttons.append(
                [InlineKeyboardButton(text=f'Remove {cart_item.name}', callback_data=cart_item.id)],
            )
        message_text += f'*Total price*: {cart.formatted_price}'
        buttons.extend((
            [InlineKeyboardButton(text='Checkout', callback_data=CHECKOUT_CALLBACK_DATA)],
            [InlineKeyboardButton(text='Back to menu', callback_data=PRODUCT_LIST_CALLBACK_DATA)],
        ))

        update.callback_query.message.reply_text(
            text=message_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN,
        )
        update.callback_query.delete_message()


def serialize_product_id_and_amount(product_id: str, amount: int) -> str:
    """
    Convert information about product and its amount into JSON string.

    Used to pass it as a callback query data.
    """
    return json.dumps({'id': product_id, 'amount': amount})


def deserialize_product_id_and_amount(serialized_data: str) -> tuple:
    """Extract information about product ID and it's amount from a JSON string."""
    deserialized_data = json.loads(serialized_data)
    return deserialized_data['id'], deserialized_data['amount']


def shop_distance_calculator(longitude: float, latitude: float) -> Callable:
    """Create a function that calculates the distance between given position and arbitrary shop."""
    def shop_distance(shop_entry: Entry) -> int:
        """Calculate the distance to provided shop in meters."""
        user_location = (longitude, latitude)
        shop_location = (shop_entry.fields['Longitude'], shop_entry.fields['Latitude'])

        return int(distance(user_location, shop_location).meters)

    return shop_distance


def start_bot() -> None:
    """Start Telegram bot."""
    users_db = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
    )
    elasticpath_api = ElasticpathAPI(client_id=settings.elasticpath_client_id)

    bot = ElasticpathShopBot(
        elasticpath_api=elasticpath_api,
        users_db=users_db,
        shop_flow=settings.shop_flow,
    )
    updater = Updater(settings.tg_bot_token)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CallbackQueryHandler(bot.handle_users_reply))
    dispatcher.add_handler(MessageHandler(Filters.location | Filters.text, bot.handle_users_reply))
    dispatcher.add_handler(CommandHandler('start', bot.handle_users_reply))

    updater.start_polling()
    updater.idle()
