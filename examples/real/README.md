# 真实模型证据：尚未生成

用户明确选择先完成离线验证，真实模型稍后配置。本次未调用真实模型，也没有产生真实模型输出或 Trace。

待配置 MODEL_ENDPOINT、MODEL_NAME、MODEL_API_KEY 后，按根目录 README 的 real 命令运行两条路径：

1. budget-replan：实际观察 12.00 超限后，模型改选 8.00，重估并保存或明确停止。
2. tool-failure：实际生成失败后，模型保留检索成果并选择替代或停止。

只有实际命中目标路径才能完成 T046。HTTP 协议夹具测试与 Mock Trace 均不计为此处的真实证据。
