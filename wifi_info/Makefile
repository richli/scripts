WIFI_SSID := $(shell grep wifissid details.tex | cut -d{ -f3 | cut -d} -f1)
WIFI_PASS := $(shell grep wifipass details.tex | cut -d{ -f3 | cut -d} -f1)
WIFI_SEC := $(shell grep '{\\wifisec}' details.tex | cut -d{ -f3 | cut -d} -f1)

.PHONY : clean all

all: info.pdf

wifi.eps:
	# https://code.google.com/p/zxing/wiki/BarcodeContents#Wifi_Network_config_%28Android%29
	qrencode -o $@ -t EPS -l Q -d 300 'WIFI:T:$(WIFI_SEC);S:$(WIFI_SSID);P:$(WIFI_PASS);;'

wifi.pdf: wifi.eps
	convert $^ $@

info.pdf: info.tex wifi.pdf
	latexmk

clean:
	latexmk -C
	rm -f wifi.{eps,pdf}
