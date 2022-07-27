# intagram-follower-crawler
 
## インストール
```shell
pip install -r requirements.txt
cp .env.sample .env
# クロールに使うアカウントを設定する
```

## 実行
```shell
python main.py anriworld

# headlessせずに実行
python main.py anriworld -dh
```
結果が`instagram_influencer_follower_{account_id}_{unixtime}.csv`に書き出される

3秒ごとにfollowerページをスクロールしてデータを取得する(途中再開はできないので注意)