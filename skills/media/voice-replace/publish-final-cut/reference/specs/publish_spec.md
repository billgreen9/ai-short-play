# 发布规范

- 只发布 swap 成功后的成片。
- `output_url` 写入 media_assets.kind=final_cut，供其他系统按 run_id 拉取。
- run.py 不访问对象存储。
