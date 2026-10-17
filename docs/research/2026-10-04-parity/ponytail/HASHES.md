# Exact skill SHA-256 comparison

Retrieved 2026-10-04. Hashes are whole-file bytes. Body equality separately removes YAML frontmatter and normalizes CRLF to LF; it is not byte equality.

| File | Installed 2.0.0 SHA-256 | Locked upstream 356918eba965ee1eac64bd3a7f0dd02108350de5 SHA-256 | Requested upstream c982cd411abb53323c4baa1baa3c2f020b8d0b08 SHA-256 |
|---|---|---|---|
| `skills/ponytail/SKILL.md` | `3d413849a55a3bdd8b01c860b5ae4a2f2b0cacfe1bfc0c97439ecc05e92219d7` | `1316a2f3f95741d2300b116fe0c2d81ce4a9568656ed0a62643f54aaf09957f2` | `1316a2f3f95741d2300b116fe0c2d81ce4a9568656ed0a62643f54aaf09957f2` |
| `skills/ponytail-review/SKILL.md` | `5e0fd5dc55adba28f503645c3492a2d566d9521f28bece92db5d25ebbfb9f173` | `40df33b58fc6ef889b93585733feb9566b76e9586efa7f376785c1e995197ac0` | `7f8bfd0da3ba7c6fe0cd0de53e6f910adfef52166c6e99d7fa4de3360650b9b6` |
| `skills/ponytail-audit/SKILL.md` | `1e7348762f289ddae0fd785dccb66212ae127debdd3c0c6dc39691866ff5fe1d` | `5560b8e383dbe2ddfddc873a1e2bf2e586e23e0cd7d995537482b2315331f6d1` | `554b7ac9c78a6b1a5e6b2bf0ba67eedf092baf71e465d03e591d0cfeb7947774` |
| `skills/ponytail-debt/SKILL.md` | `616e72782c3b7968888430fd8314899c175ea79ec16073d638fa582b4d6140b2` | `c84fba75f0ca12bfe83f9a78ea02fd125c5dd3f1fbb18124105a489937f284e6` | `d3611761039bdb2955e31856834feeec6ed5483a3fc64576e9a166f949a131d1` |
| `skills/ponytail-gain/SKILL.md` | `eecde3e21a9ce7c94300a288cce1a5e5251f4913c0abefdd99ee279b96a313d8` | `24e01d1c9715cb136ba1c4f1e52a95940c0193558b876828e537736480d6408b` | `24e01d1c9715cb136ba1c4f1e52a95940c0193558b876828e537736480d6408b` |
| `skills/ponytail-help/SKILL.md` | `ed807f06935af6637896d2a91d9184bd0445d773bdeda2983d622d6d8d0ac2de` | `2264d1615117b02b0fd5a69ec84cd2757006471a78e4d6c22eed6d581c1d37a4` | `23d9baf1b9a9464b40ebe1b5b50752795210b934fc8e248e791496e4c9a39fd2` |

All six installed files differ byte-for-byte from their locked originals (description frontmatter reformatted and `disable-model-invocation: true` added). All six normalized bodies match the locked version. Only ponytail and ponytail-gain bodies also match the requested upstream revision. See `skill-parity.diff`.

## Other relevant installed files

| File | SHA-256 |
|---|---|
| `.codex-plugin/plugin.json` | `a10c8ade62558486c5356827235484ebf31fddf8e0f0e6081f1241dc6113f6ef` |
| `LICENSE` | `cf528a33542cc035fc8063e7e924505d4b8464f4361d9ef18f6728918594254f` |
| `README.md` | `64be2c0ed01fdf078f8d08313753e77f105aecd3c743948376867272e8b63c2c` |
| `skills/code-simplification/SKILL.md` | `bd78ae65195fee4a03ae407d31ace2d8f1cf44e83b40e3df4fb0429c8cb0c7b4` |
| `skills/entry-ponytail/SKILL.md` | `fee9e0ce8e9bc0eb93af29b452acc0ff86373c2934a875e208956a6d2f095aeb` |
| `third_party_licenses/ponytail-LICENSE` | `fb1bc6909ac3ef82d5c22106e32ef682b0cff66788fa915fb9b53b15c9d2f3ab` |
| `THIRD_PARTY_NOTICES.md` | `32ecfd0a9727ef2cb2419378cd3b56d072f8c0dcc320b4ce564757139517cb0c` |
| `UPSTREAM_LOCK.json` | `531f097690848bf7d17562f0158912e6c309c3af69cbc9ce510b96cf3632e6e3` |
