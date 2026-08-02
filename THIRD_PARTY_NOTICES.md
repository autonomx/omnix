# Third-Party Notices

## Wallie

The Omnix Desktop Companion architecture was informed by the public Wallie project:

- Project: Wallie
- Repository: `Alradyin/wallie-V2`
- License: MIT
- Copyright: Copyright (c) 2026 Wallie Contributors

Omnix uses a clean-room implementation of the relevant observer, activity, attention, restraint, scene-memory, and commentary concepts. No Wallie runtime dependency is included.

The Wallie license permits use, modification, distribution, and sublicensing subject to retaining its copyright and permission notice in substantial copied portions. Any future Omnix source file substantially derived from Wallie code must include the applicable MIT notice in that file or an adjacent license notice.

Wallie MIT license text:

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Kyutai Unmute

The optional Kyutai live-STT adapter follows the public streaming protocol and endpointing approach demonstrated by the Kyutai Unmute project.

- Project: `kyutai-labs/unmute`
- Copyright: Copyright (c) 2025 kyutai
- License: MIT

Unmute MIT license text:

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Kyutai STT model weights

The proof-of-concept configuration references the separately downloaded model:

- Model: `kyutai/stt-1b-en_fr-candle`
- Publisher: Kyutai
- Model-weight license: Creative Commons Attribution 4.0 International (CC BY 4.0)

The model weights are not bundled in this repository. Deployments that download, redistribute, or expose the model must preserve attribution and comply with the model card and license terms for the exact pinned revision they use.

## Moshi server

The Kyutai adapter expects an independently deployed `moshi-server`. The server and its dependencies are not vendored in Omnix. Review and retain the applicable upstream notices for the exact Moshi revision and container used by a deployment.
