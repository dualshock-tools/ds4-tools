# ds4-tools

This repo contains some Python scripts I use to play and reverse-engineer the
DualShock 4 controller.

## Warning

Use these files at your own risk and be ready to throw away your controller
because it could stop working.

They have been tested on **only two DS4** on planet Earth, so any slight change
of your DS4 w.r.t mine can lead to bricking it.

## Contents

- `ds4-tool.py` can be used to play with undocumented commands of your DualShock 4
- `ds4-calibration-tool.py` can be used to calibrate analog sticks or triggers. It has a nice TUI.

## How to use them

1. Clone the repo and go into the directory

```
$ git clone <repo link>
$ cd ds4-tools
```

2. Install dependencies
```
$ virtualenv venv
$ . venv/bin/activate
$ pip install -r requirements.txt
```

3. Play with the scripts
```
$ python3 script.py
```

## Example

```
$ python3 ds4-tool.py info

[+] Waiting for device VendorId=054c ProductId=09cc
Compiled at: Sep 21 2018 04:50:51
hw_ver:0100.b400
sw_ver:00000001.a00a sw_series:2010
code size:0002a000

```

