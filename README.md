# 🪵🪵🪵

> What rolls down stairs, alone or in pairs, and over your neighbor's dog?
> What's great for a snack, And fits on your back?
> It's Log Log Log!

I needed line wrapping in my tty with fast access, so why not make a log that
supports egregious sizes and low seek times?

## ⏩

```bash
# makes log.log.log from /var/log
make log
```

## TODO

- [ ] Fix main functionality
  - [ ] Some dickhead AI flattened my btree
  - [x] Move Array to different project so AI stops pissing about with it
- [ ] Testing
  - [x] Move `log_log_log.sh` into Python (`tools.all_logs`)
- [ ] Features
  - [ ] Pane (tail with width and height)
  - [ ] Scrolly (pane + vertical scrollbar)
  - [ ] Scrollx (no wrap, char wrap, word wrap)
  - [ ] Search
  - [ ] Timestamped
- [ ] Line formatters (plain, ansi-stripped, jsonpp?...)
- [ ] Async/non-blocking design
  - [ ] Make log processing async to avoid blocking
  - [ ] Support streaming updates
- [ ] Interface design and view mixins
  - [ ] Proper view mixin architecture
  - [ ] Pipeable view types (search, filter, transform)
- [ ] Multiple display backends
  - [ ] WebSocket/FastAPI for web UIs
  - [ ] Pipe commands for shell integration
  - [ ] Rich for direct terminal display
  - [ ] Textual for interactive TUIs
  - [ ] Curses/urwid fallbacks
- [ ] Python logging integration
  - [ ] Direct logger handlers
  - [ ] Log level filtering and formatting
- [ ] Cache management
  - [ ] Periodic cleanup of cache directories
  - [ ] Check file existence by inode lookup
  - [ ] Handle file rotation and moves

