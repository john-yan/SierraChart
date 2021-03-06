# SierraChart

SierraChart is a powerful tool for trading the markets. And it also provide a DTC protocol (Data and Trading Communications Protocol), which can be used by third parties to extend its functionality. This repo provides a few examples on how to use DTC to communicate with sierra chart instance.

DTCClient.py implements `DTCClient` and `DTCClientAsync` providing a queued asynchronized client.

HistoricalDataDownloader.py implements a `DownloadAsync` class that can be used to download historical data from sierra chart. eg.
```
  python3 HistoricalDataDownloader.py --userpass=userpass --address=$SC_IP -p 11098 -s ESH21-CME -e CME --record_interval=INTERVAL_5_MINUTE
```
NOTE: If $SC_IP is not `127.0.0.1`, you need to be careful, because sierra chart will see this extra connection as a extra machine and therefore block the connection unless you pay extra $$. To get around this, you need a proxy to forward traffic to your local `127.0.0.1` ip. One of the easy way on windows 10 is to use netsh command on powershell. [https://docs.microsoft.com/en-us/windows-server/networking/technologies/netsh/netsh-interface-portproxy].

Running `DTCClient.py` itself will simply log data to disk and you can process the data using a separate process.
```
python3 DTCClient.py -a $SC_IP -s ESM21-CME -f current.log
```
RealTimeLogToTickData.py Converts log file produced by DTCClient to tick csv file. eg.
```
python3 RealTimeLogToTickData.py -i current.log -o current.tick -f
```

Compute.py takes the log file generated by DTCClient.py and realtime computes Candle stick (OHLC) chart and imbalance chart.
```
  python3 Compute.py -t $TYPE -i $ES_LOG -H $ES_HFILE -R $ES_RFILE -p $PERIOD -f
```

bokeh-server2.py helps to visualize the OHLC chart and imbalance chart.
```
  bokeh serve ./bokeh-server2.py --address=192.168.130.107 --allow-websocket-origin=192.168.130.107:5006
```
