# intagram-follower-crawler
 
## Install & Setup
```shell
pip install -r requirements.txt
cp .env.sample .env
# account setting for crawl
```

## Execute
```shell
python main.py anriworld

# disable headless
python main.py anriworld -dh

# crawl interval 5s
python main.py anriworld -i=5
```

## API Crawl Mode
This mode executes the API directly using the cookies obtained by selenium. In this case, it is possible to specify the limit to retrieve and the ID to resume in the middle of the process.
```shell
python main.py anriworld -mode='api'

# limit & restart max_id
python main.py anriworld -mode='api' -l=100 -m=QVFEV29lV0RWTElnaG9QQ25PWHMwcS0yTUlpbXdwYW1RRkVvaVo4UktlWmtmbGl0al9MRUpST3A0OWhiSnRUZExjWFotY01LR3pRMnBTQWdneGdob0hsaQ==
```

## Additions to the file on restart
If you want to append to the specified file when restart, you can specify it with the file option.
```shell
python main.py anriworld -mode='api' -l=100 -m=QVFEV29lV0RWTElnaG9QQ25PWHMwcS0yTUlpbXdwYW1RRkVvaVo4UktlWmtmbGl0al9MRUpST3A0OWhiSnRUZExjWFotY01LR3pRMnBTQWdneGdob0hsaQ== -f=instagram_influencer_follower_anriworld_0000000000.csv
```

## Options
```python
parser.add_argument("account_id")
parser.add_argument("-dh", "--disable_headless", action='store_true')
parser.add_argument("-i", "--interval", type=int, default=5)
parser.add_argument("-f", "--file")
parser.add_argument("-m", "--max_id")
parser.add_argument("-l", "--limit", type=int, default=100)
parser.add_argument("-mode", default='scroll')

if 'api' in mode:
    ic.get_followers_by_api(account_id=account_id, interval=interval, limit=limit, max_id=max_id, filename=file)
else:
    ic.get_followers_by_scroll(account_id=account_id, interval=interval)
```
Results are written to `instagram_influencer_follower_{account_id}_{unixtime}.csv  
Scroll down the follower page every 3 seconds to retrieve data (note that it is not possible to resume in the middle of the page)