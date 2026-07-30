# 🪵🪵🪵

![log](log.webp)

> What rolls down stairs, alone or in pairs, and over your neighbor's dog?
> What's great for a snack, And fits on your back?
> It's Log Log Log!

I needed line wrapping in my tty with fast access, so why not make a log that
supports egregious sizes and low seek times?

## ⏩

```bash
# makes log.log.log from /var/log
make log
# run the demo
./demos/textual_demo.py
# print a wrapped log view
python -m logloglog logs/log.log.log --width 80
```

## 🔗 links

* [📺 video](https://asciinema.org/a/751364)
* [🏠 home](https://bitplane.net/dev/python/logloglog)
  * [📖 pydoc](https://bitplane.net/dev/python/logloglog/pydoc)
* [🐍 pypi](https://pypi.org/project/logloglog)
* [🐱 github](https://github.com/bitplane/logloglog)

## TODO

- [x] Textual demo
- [x] Async/non-blocking design
- [ ] Multiple display backends
- [ ] Python logging integration
  - [ ] Direct logger handlers
  - [ ] Log level filtering and formatting
- [ ] Cache management
  - [ ] Periodic cleanup of cache directories
  - [ ] Check file existence by inode lookup
  - [ ] Handle file rotation and moves
