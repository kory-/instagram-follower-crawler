import logging
import re
import sys
import time
import json
import urllib.parse
from tempfile import mkdtemp
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from csv import DictWriter
import os
from dotenv import load_dotenv
import argparse
import chromedriver_binary
import requests

load_dotenv()
parser = argparse.ArgumentParser()

parser.add_argument("account_id")
parser.add_argument("-dh", "--disable_headless", action='store_true')
parser.add_argument("-i", "--interval", type=int, default=5)
parser.add_argument("-f", "--file")
parser.add_argument("-m", "--max_id")
parser.add_argument("-l", "--limit", type=int, default=100)
parser.add_argument("-mode", default='scroll')
args = parser.parse_args()

USER_ID = os.getenv('USER_ID')
PASSWORD = os.getenv('PASSWORD')


def set_logger(name=None):
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(lambda record: record.levelno <= logging.INFO)

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setLevel(logging.WARNING)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(stdout_handler)
    logger.addHandler(stderr_handler)


class InstagramCrawler:
    INSTAGRAM_BASE_URL = "https://www.instagram.com/"

    def __init__(self, headless):
        self.driver = self.get_driver(headless)

    def login(self, id, password):
        logger.info(f"crawler account login start")
        login_url = self.INSTAGRAM_BASE_URL + 'accounts/login'
        self.driver.get(login_url)

        input_id = WebDriverWait(self.driver, timeout=30).until(lambda d: d.find_element(by=By.NAME, value="username"))
        input_pw = WebDriverWait(self.driver, timeout=30).until(lambda d: d.find_element(by=By.NAME, value="password"))

        input_id.send_keys(id)
        input_pw.send_keys(password)

        time.sleep(1)

        button_login = WebDriverWait(self.driver, timeout=30).until(
            lambda d: d.find_element(By.XPATH, '//*[@id="loginForm"]/div/div[3]/button')
        )

        time.sleep(1)
        button_login.click()

        time.sleep(5)

        if self.driver.current_url == self.INSTAGRAM_BASE_URL \
                or self.driver.current_url == 'https://www.instagram.com/accounts/onetap/?next=%2F' \
                or self.driver.current_url == 'https://www.instagram.com/#reactivated':
            logger.info(f"crawler account login success")
            return True
        else:
            raise Exception("login failed")

    def get_user(self, account_id):
        url = self.INSTAGRAM_BASE_URL + account_id
        self.driver.get(url)

    def get_driver(self, headless):
        capabilities = DesiredCapabilities.CHROME
        capabilities['goog:loggingPrefs'] = {'performance': 'ALL'}
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless')
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1980x1030")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-dev-tools")
        options.add_argument("--no-zygote")
        options.add_argument(f"--user-data-dir={mkdtemp()}")
        options.add_argument(f"--data-path={mkdtemp()}")
        options.add_argument(f"--disk-cache-dir={mkdtemp()}")
        driver = webdriver.Chrome(options=options, desired_capabilities=capabilities)

        return driver

    def driver_quit(self):
        time.sleep(1)
        self.driver.quit()

    def get_followers_by_scroll(self, account_id, interval=5):
        logger.info(f"{account_id} 's follower crawl start")
        self.get_user(account_id)

        follower_button = WebDriverWait(self.driver, timeout=30).until(
            lambda d: d.find_element(by=By.XPATH, value="//a[contains(@href, '/followers')]"))
        follower_button.click()

        time.sleep(3)

        scroll_box = self.driver.find_element(By.XPATH, "//div[@role='dialog']//ul/parent::div")

        headersCSV = ["pk", "username", "full_name", "is_private", "profile_pic_url", "profile_pic_id", "is_verified",
                      "has_anonymous_profile_picture", "has_highlight_reels", "account_badges", "similar_user_id",
                      "latest_reel_media"]
        with open(fr'instagram_influencer_follower_{account_id}_{int(time.time())}.csv', 'a', newline='') as f:
            writer = DictWriter(f, fieldnames=headersCSV, extrasaction='ignore')
            writer.writeheader()

            retry, scroll, last_ht, ht = 0, 0, 0, 1
            while retry != 5:
                logger.info(f"page {scroll}")
                last_ht = ht
                ht = self.driver.execute_script(""" 
                            arguments[0].scrollTo(0, arguments[0].scrollHeight);
                            return arguments[0].scrollHeight; """, scroll_box)

                time.sleep(interval)

                logs_raw = self.driver.get_log("performance")
                logs = [json.loads(lr["message"])["message"] for lr in logs_raw]

                def log_filter(log_):
                    pattern = r"https?://i.instagram.com/api/v1/friendships/[\d]+/followers/"
                    return (
                            log_["method"] == "Network.responseReceived"
                            and "json" in log_["params"]["response"]["mimeType"]
                            and len(re.findall(pattern, log_["params"]["response"]["url"])) > 0
                    )

                for log in filter(log_filter, logs):
                    request_id = log["params"]["requestId"]
                    resp_url = log["params"]["response"]["url"]
                    logger.info(f"query url {resp_url}")

                    try:
                        response_body = self.driver.execute_cdp_cmd("Network.getResponseBody",
                                                                    {"requestId": request_id})
                    except Exception as e:
                        continue

                    response_json = json.loads(response_body['body'])

                    users = response_json['users'] if 'users' in response_json else []
                    for user in users:
                        logger.info(f"id: {user['pk']} name: {user['username']}")
                        writer.writerow(user)

                scroll += 1
                logger.info(f"last hight: {last_ht} hight: {ht} retry: {retry}")
                if last_ht == ht:
                    time.sleep(600)
                    retry = retry + 1
                else:
                    retry = 0

        f.close()
        logger.info(f"{account_id} 's follower crawl end")

    def get_followers_by_api(self, account_id, interval=5, limit=100, max_id=None, filename=None):
        resp_url = ''
        logger.info(f"{account_id} 's follower crawl start")
        cookies = {
            cookie['name']: cookie['value']
            for cookie in self.driver.get_cookies()
        }

        self.get_user(account_id)

        follower_button = WebDriverWait(self.driver, timeout=30).until(
            lambda d: d.find_element(by=By.XPATH, value="//a[contains(@href, '/followers')]"))
        follower_button.click()
        time.sleep(3)

        logs_raw = self.driver.get_log("performance")
        logs = [json.loads(lr["message"])["message"] for lr in logs_raw]

        def log_filter(log_):
            pattern = r"https?://i.instagram.com/api/v1/friendships/[\d]+/followers/"
            return (
                    log_["method"] == "Network.responseReceived"
                    and "json" in log_["params"]["response"]["mimeType"]
                    and len(re.findall(pattern, log_["params"]["response"]["url"])) > 0
            )

        for log in filter(log_filter, logs):
            request_id = log["params"]["requestId"]
            resp_url = log["params"]["response"]["url"]
            logger.info(f"query url {resp_url}")

            try:
                response_body = self.driver.execute_cdp_cmd("Network.getResponseBody",
                                                            {"requestId": request_id})
            except Exception as e:
                continue

            response_json = json.loads(response_body['body'])

        time.sleep(interval)

        next_max_id = response_json['next_max_id'] if 'next_max_id' in response_json else None

        headersCSV = ["pk", "username", "full_name", "is_private", "profile_pic_url", "profile_pic_id", "is_verified",
                      "has_anonymous_profile_picture", "has_highlight_reels", "account_badges", "similar_user_id",
                      "latest_reel_media"]

        pattern = r"https?://i.instagram.com/api/v1/friendships/([\d]+)/followers/"
        pk = re.findall(pattern, resp_url)[0]
        logger.info(f"crawl target id: {pk}")

        if not filename:
            filename = fr'instagram_influencer_follower_{account_id}_{int(time.time())}.csv'

        with open(filename, 'a', newline='') as f:
            writer = DictWriter(f, fieldnames=headersCSV, extrasaction='ignore')
            if not max_id:
                writer.writeheader()

                users = response_json['users'] if 'users' in response_json else []
                for user in users:
                    logger.info(f"id: {user['pk']} name: {user['username']}")
                    writer.writerow(user)
            else:
                next_max_id = max_id

            while next_max_id is not None:
                url = f'https://i.instagram.com/api/v1/friendships/{pk}/followers/?count={limit}&search_surface=follow_list_page&max_id={next_max_id}'
                print(url)
                response = requests.get(
                    url,
                    headers={
                        'x-ig-app-id': '936619743392459',
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.134 Safari/537.36'},
                    cookies=cookies)

                response_json = response.json()
                users = response_json['users'] if 'users' in response_json else []
                for user in users:
                    logger.info(f"id: {user['pk']} name: {user['username']}")
                    writer.writerow(user)

                next_max_id = response_json['next_max_id'] if 'next_max_id' in response_json else None
                logger.info(f"next_max_id: {next_max_id}")
                time.sleep(interval)

        f.close()
        logger.info(f"{account_id} 's follower crawl end")


    def get_followers_by_json(self, account_id, interval=5, limit=50, max_id=None, filename=None):

        resp_url = ''
        logger.info(f"{account_id} 's follower crawl start")
        cookies = {
            cookie['name']: cookie['value']
            for cookie in self.driver.get_cookies()
        }

        self.get_user(account_id)


        follower_button = WebDriverWait(self.driver, timeout=30).until(
            lambda d: d.find_element(by=By.XPATH, value="//a[contains(@href, '/followers')]"))
        follower_button.click()
        time.sleep(3)

        logs_raw = self.driver.get_log("performance")
        logs = [json.loads(lr["message"])["message"] for lr in logs_raw]

        def log_filter(log_):
            pattern = r"https?://i.instagram.com/api/v1/friendships/[\d]+/followers/"
            return (
                    log_["method"] == "Network.responseReceived"
                    and "json" in log_["params"]["response"]["mimeType"]
                    and len(re.findall(pattern, log_["params"]["response"]["url"])) > 0
            )

        for log in filter(log_filter, logs):
            resp_url = log["params"]["response"]["url"]

        headersCSV = ["pk", "username", "full_name", "profile_pic_url", "is_verified",
                      "followed_by_viewer", "requested_by_viewer"]

        pattern = r"https?://i.instagram.com/api/v1/friendships/([\d]+)/followers/"
        pk = re.findall(pattern, resp_url)[0]
        logger.info(f"crawl target id: {pk}")

        if not filename:
            filename = fr'instagram_influencer_follower_{account_id}_{int(time.time())}.csv'

        with open(filename, 'a', newline='') as f:
            writer = DictWriter(f, fieldnames=headersCSV, extrasaction='ignore')
            if not max_id:
                writer.writeheader()

                users, next_max_id = self.get_users_json(cookies, limit, None, pk)
                for user in users:
                    _user = user['node']
                    _user['pk'] = _user['id']
                    logger.info(f"id: {_user['pk']} name: {_user['username']}")
                    writer.writerow(_user)
                time.sleep(interval)
            else:
                next_max_id = max_id

            while next_max_id is not None:
                users, next_max_id = self.get_users_json(cookies, limit, next_max_id, pk)

                if not next_max_id:
                    logger.info(f"next_max_id: {next_max_id}")
                    break

                if len(users) == 0:
                    raise Exception("account rate limit")

                for user in users:
                    _user = user['node']
                    _user['pk'] = _user['id']
                    logger.info(f"id: {_user['pk']} name: {_user['username']}")
                    writer.writerow(_user)

                logger.info(f"next_max_id: {next_max_id}")
                time.sleep(interval)

        f.close()
        logger.info(f"{account_id} 's follower crawl end")

    def get_followers_json_link(self, account_id, count, after=None):
        follower_url = 'https://www.instagram.com/graphql/query/?query_id=17851374694183129&id={}&first={}'.format(
            urllib.parse.quote(account_id),
            count
        )

        if after:
            follower_url = follower_url + '&after={}'.format(urllib.parse.quote(after))

        return follower_url

    def get_users_json(self, cookies, limit, next_max_id, pk):
        url = self.get_followers_json_link(pk, limit, next_max_id)
        print(url)
        response = requests.get(
            url,
            headers={
                'x-csrftoken': self.driver.get_cookie('csrftoken').get('value'),
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.134 Safari/537.36'},
            cookies=cookies)
        response_json = response.json()
        users = response_json.get('data', {}).get('user', {}).get('edge_followed_by', {}).get('edges', [])
        next_max_id = False
        if response_json.get('data', {}).get('user', {}).get('edge_followed_by', {}).get('page_info', {}).get('has_next_page', False):
            next_max_id = response_json.get('data').get('user').get('edge_followed_by').get('page_info').get('end_cursor', None)
        return users, next_max_id


if __name__ == "__main__":

    set_logger()
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    try:
        account_id = args.account_id
        interval = args.interval
        max_id = args.max_id
        limit = args.limit
        file = args.file
        mode = args.mode
        headless = False if args.disable_headless else True

        logger.info(f"{account_id} 's follower crawl")

        ic = InstagramCrawler(headless=headless)

        ic.login(USER_ID, PASSWORD)

        if 'api' in mode:
            ic.get_followers_by_api(account_id=account_id, interval=interval, limit=limit, max_id=max_id, filename=file)
        elif 'json' in mode:
            ic.get_followers_by_json(account_id=account_id, interval=interval, limit=limit, max_id=max_id, filename=file)
        else:
            ic.get_followers_by_scroll(account_id=account_id, interval=interval)
        ic.driver_quit()

    except Exception as e:
        logger.exception(f"Failed to function {e}")
