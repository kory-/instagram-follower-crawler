import logging
import re
import sys
import time
import json
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

load_dotenv()
parser = argparse.ArgumentParser()

parser.add_argument("account_id")
parser.add_argument("-dh", "--disable_headless", action='store_true')
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
        login_url = self.INSTAGRAM_BASE_URL + ''
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

        if self.driver.current_url == login_url or self.driver.current_url == 'https://www.instagram.com/accounts/onetap/?next=%2F':
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

    def follower_user(self, account_id):
        logger.info(f"{account_id} 's follower crawl start")
        self.get_user(account_id)

        follower_button = WebDriverWait(self.driver, timeout=30).until(
            lambda d: d.find_element(by=By.XPATH, value="//a[contains(@href, '/followers')]"))
        follower_button.click()

        time.sleep(3)

        scroll_box = self.driver.find_element(By.XPATH, "//div[@role='dialog']//ul/parent::div")

        headersCSV = ["pk", "username", "full_name", "is_private", "profile_pic_url", "profile_pic_id", "is_verified",
                      "has_anonymous_profile_picture", "has_highlight_reels", "account_badges", "latest_reel_media"]
        with open(fr'instagram_influencer_follower_{account_id}_{int(time.time())}.csv', 'a', newline='') as f:
            writer = DictWriter(f, fieldnames=headersCSV)
            writer.writeheader()

            scroll, last_ht, ht = 0, 0, 1
            while last_ht != ht:
                logger.info(f"page {scroll}")
                last_ht = ht
                ht = self.driver.execute_script(""" 
                            arguments[0].scrollTo(0, arguments[0].scrollHeight);
                            return arguments[0].scrollHeight; """, scroll_box)
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
                    # resp_url = log["params"]["response"]["url"]
                    try:
                        response_body = self.driver.execute_cdp_cmd("Network.getResponseBody",
                                                                    {"requestId": request_id})
                    except Exception as e:
                        continue

                    responce_json = json.loads(response_body['body'])

                    users = responce_json['users'] if 'users' in responce_json else []
                    for user in users:
                        print(user)
                        writer.writerow(user)

                scroll += 1
                print(last_ht, ht)
        f.close()
        logger.info(f"{account_id} 's follower crawl end")


if __name__ == "__main__":

    set_logger()
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    try:
        account_id = args.account_id
        headless = False if args.disable_headless else True

        logger.info(f"{account_id} 's follower crawl")

        ic = InstagramCrawler(headless=headless)
        ic.login(USER_ID, PASSWORD)
        ic.follower_user(account_id)
        ic.driver_quit()

    except Exception as e:
        logger.exception(f"Failed to function {e}")
