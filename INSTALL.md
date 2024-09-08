# Installation instructions

Tested on Fedora 40:

First, install required packages.
```
dnf install -y python3-pip
python3 -m pip install --index-url https://test.pypi.org/simple/ autopie --extra-index-url=https://pypi.python.org/simple
```

Create your configuration:
```
mkdir -p ~/.config/autopie && \
cp /usr/local/lib/python3.12/site-packages/autopie/config.toml.template ~/.config/autopie/config.toml
```
Consider also using `secrets.env` (template in the same place).
```
cp /usr/local/lib/python3.12/site-packages/autopie/secrets.env.template ~/.config/autopie/secrets.env
```

Edit `~/.config/autopie/config.toml`, possibly also `~/.config/autopie/secrets.env`

Run `autopie` command.
