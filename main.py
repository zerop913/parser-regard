import requests
import bs4
import logging
import csv
import os
import time
from urllib.parse import urlparse
import ntpath

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('regard')

class Client:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36',
            'Accept-Language': 'ru'
        }
        self.result = []
        self.image_dir = 'images/videokarty'
        os.makedirs(self.image_dir, exist_ok=True)

    def create_csv_file(self):
        if not os.path.exists('videokarty.csv'):
            with open('videokarty.csv', 'w', newline='', encoding='utf-8') as csv_file:
                csv_writer = csv.writer(csv_file)
                csv_writer.writerow(['Product Title', 'Product Image', 'Price', 'Characteristics'])

    def append_to_csv(self, data):
        with open('videokarty.csv', 'a', newline='', encoding='utf-8') as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(data)

    def product_exists(self, data):
        with open('videokarty.csv', 'r', newline='', encoding='utf-8') as csv_file:
            csv_reader = csv.reader(csv_file)
            for row in csv_reader:
                if row[0] == data[0] and row[3] == data[3] and row[2] == data[2]:
                    return True
        return False

    def load_page(self, page: int = 1):
        url = f'https://www.regard.ru/catalog/1013/videokarty?page={page}'
        try:
            res = self.session.get(url=url)
            res.raise_for_status()
            return res.text
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning('Too Many Requests. Waiting...')
                time.sleep(60)
                return self.load_page(page)
            else:
                raise

    def parse_page(self, start_page: int = 1):
        page = start_page
        while True:
            text = self.load_page(page)
            soup = bs4.BeautifulSoup(text, 'lxml')
            container = soup.select('div.Card_wrap__hES44.Card_listing__nGjbk.ListingRenderer_listingCard__DqY3k')
            if not container:
                logger.info('No more products on page %d. Exiting.', page)
                break

            for block in container:
                self.parse_block(block=block)

            page += 1
            time.sleep(5)

    def load_more(self):
        try:
            next_button = self.session.get('https://www.regard.ru/catalog/1013/videokarty', headers={'X-Requested-With': 'XMLHttpRequest'})
            next_button.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning('Too Many Requests. Waiting...')
                time.sleep(60)
                self.load_more()
            else:
                raise

    def parse_block(self, block):
        try:
            url_block = block.select_one('a.CardText_link__C_fPZ.link_black')
            if not url_block:
                logger.error('no url_block')
                return

            relative_url = url_block.get('href')
            if not relative_url:
                logger.error('no href')
                return

            full_url = 'https://www.regard.ru' + relative_url

            product_page = self.session.get(full_url)
            product_page.raise_for_status()

            product_soup = bs4.BeautifulSoup(product_page.text, 'lxml')

            product_title = product_soup.select_one('h1.Product_title__42hYI')
            price_block = product_soup.select_one('div.PriceBlock_priceBlock__178uq')
            char_blocks = product_soup.select('div.CharacteristicsSection_content__5BpzM div.CharacteristicsItem_item__QnlK2')

            slider_image = product_soup.select_one('img.BigSlider_slide__image__2qjPm')

            if slider_image:
                image_url = 'https://www.regard.ru' + (slider_image.get('data-src', '').replace('/160', '/716') or slider_image['src'].replace('/160', '/716'))
            else:
                logger.warning('Skipping product without image: %s', product_title.text.strip() if product_title else '')
                return

            if not image_url or image_url.startswith('data:image'):
                logger.warning('Skipping product without image: %s', product_title.text.strip() if product_title else '')
                return

            # Save image to folder
            image_filename = os.path.basename(urlparse(relative_url).path) + '.png'
            image_path = os.path.join(self.image_dir, image_filename)
            if not os.path.exists(image_path):
                response = self.session.get(image_url)
                response.raise_for_status()
                with open(image_path, 'wb') as f:
                    f.write(response.content)

            data = [
                product_title.text.strip() if product_title else '',
                os.path.join(self.image_dir, image_filename).replace('\\', '/'),  # Корректный путь к изображению
                price_block.text.strip() if price_block else '',
                '\n'.join(f'{char_block.contents[0].text.replace("&nbsp", " ").strip()} - {char_block.contents[1].text.replace("&nbsp", " ").strip()}' for char_block in char_blocks)
            ]

            if not self.product_exists(data):
                self.append_to_csv(data)
            else:
                logger.warning('Skipping duplicate product: %s', data[0])

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 410:
                logger.warning('Product is no longer available: %s', full_url)
            else:
                logger.error('HTTP Error: %s', e.response.status_code)
                if e.response.status_code == 429:
                    logger.warning('Too Many Requests. Waiting...')
                    time.sleep(60)
                    self.parse_block(block)
                else:
                    raise

        time.sleep(5)

    def run(self):
        self.create_csv_file()
        self.parse_page()

        with open('videokarty.csv', 'r', newline='', encoding='utf-8') as csv_file:
            csv_reader = csv.reader(csv_file)
            num_total_products = len(list(csv_reader))
            num_added_products = num_total_products - 1
            logger.info('Added %d/%d products', num_added_products, num_total_products)

if __name__ == '__main__':
    parser = Client()
    parser.run()