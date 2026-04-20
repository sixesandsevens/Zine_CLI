.PHONY: deb install-deb check-deb clean-deb

VERSION := $(shell sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -n 1)
DEB_PATH := packaging/deb/dist/zine-imposer_$(VERSION)_all.deb

deb:
	./packaging/deb/build-deb.sh

install-deb: deb
	sudo apt install -y ./$(DEB_PATH)

check-deb: deb
	./packaging/deb/check-deb.sh ./$(DEB_PATH)

clean-deb:
	rm -rf packaging/deb/dist packaging/deb/zine-imposer/usr/lib/zine-imposer/src
