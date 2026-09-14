// -*- coding: utf-8 -*-
// Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

// This file is part of Wirecloud.

// Wirecloud is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// Wirecloud is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.

// You should have received a copy of the GNU Affero General Public License
// along with Wirecloud.  If not, see <http://www.gnu.org/licenses/>.

import { GridStack, Utils } from 'gridstack';
import 'gridstack/dist/gridstack.css';

// Fix GridStack smooth scroll jitter during resize:
// GridStack's default updateScrollResize uses unthrottled smooth scrolling
// (scrollBy({ behavior: 'smooth' })) on mousemove, which queues overlapping smooth
// animations, causing erratic scroll jumping and drift until it finishes.
// Replace with instant auto-scroll only if the container actually has scrollable overflow.
if (Utils) {
    Utils.updateScrollResize = function updateScrollResize(event, el, distance) {
        const scrollEl = Utils.getScrollElement(el);
        if (!scrollEl || scrollEl.scrollHeight <= scrollEl.clientHeight) {
            return;
        }
        const height = scrollEl.clientHeight;
        const offsetTop = (scrollEl === Utils.getScrollElement()) ? 0 : scrollEl.getBoundingClientRect().top;
        const pointerPosY = event.clientY - offsetTop;
        const top = pointerPosY < distance;
        const bottom = pointerPosY > height - distance;
        if (top) {
            const step = Math.max(-15, pointerPosY - distance);
            scrollEl.scrollBy({ top: step, behavior: 'auto' });
        } else if (bottom) {
            const step = Math.min(15, pointerPosY - (height - distance));
            scrollEl.scrollBy({ top: step, behavior: 'auto' });
        }
    };
}

window.GridStack = GridStack;
