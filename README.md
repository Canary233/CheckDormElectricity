# CheckDormElectricity

- 本项目适配宁波财经学院(NBUFE)
- 使用本项目需要抓包基础。 👉[学习如何使用微信调试抓包](./PacketCapture.md)
- 本项目用于自动查询宿舍房间电量，并通过钉钉机器人发送提醒。
- 本项目由 https://github.com/Sh1rokoDev/CheckDormElectricity 修改而来

## 安装

```sh
pip install -r requirements.txt
```

## 配置

复制示例配置：

```sh
copy config.yaml.example config.yaml
```

在 `config.yaml` 中填写以下信息：

```yaml
webhook: ''
secret: ''

request_address: 'https://application.xiaofubao.com/app/electric/queryISIMSRoomSurplus'
request_timeout: 15

data_studentRoom:
  areaId: ''
  buildingCode: ''
  floorCode: ''
  roomCode: ''
  platform: ''

request_cookie: 'shiroJID=你的Cookie值'
notify_only_when_low: false
save_last_response: false
```

`webhook` 和 `secret` 可留空，留空时只在命令行打印结果，不推送钉钉。

## 抓包字段

打开电费充值页面后，在浏览器 DevTools 的 Network 面板中找到：

```text
queryISIMSRoomSurplus
```

需要从该请求中复制：

- `areaId`
- `buildingCode`
- `floorCode`
- `roomCode`
- `platform`
- Cookie 名称和值，通常为 `shiroJID=...`

注意：Cookie 必须写完整的 `名称=值`，例如：

```yaml
request_cookie: 'shiroJID=daebd9aa-7dbf-43f5-be5c-f8ac635f0cd0'
```

如果脚本提示 `请重新登录`，说明 Cookie 已失效或未填写完整，需要重新抓包更新。

## 运行

```sh
python main.py
```

正常输出示例：

```text
Time: 2026-05-27 00:42:51
学生房间电量: 333.69 度 (海曙校区x宿x x层x宿x-xxx)
{'errcode': 0, 'errmsg': 'ok'}
```

## 可选配置

修改低电量提醒阈值：

```yaml
low_threshold: 10
```

仅低电量时推送：

```yaml
notify_only_when_low: true
```

开启后，电量不低于阈值时只在命令行输出，不发送钉钉消息。接口异常、Cookie 失效、配置错误仍会推送提醒。

保存最近一次响应：

```yaml
save_last_response: true
```

启用后会在项目目录生成 `last_response_学生房间.json` 等文件。

## 提示!完成抓包后再次使用小程序查询电费可能会导致Cookie失效!建议让室友代充电费.
