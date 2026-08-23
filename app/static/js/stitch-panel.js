(function () {
    var container = document.getElementById('stitch-panel');
    var trigger = document.getElementById('stitch-reference-toggle');
    if (!container || !trigger || typeof htmx === 'undefined') {
        return;
    }

    var loading = false;

    function panelCard() {
        return container.querySelector('.stitch-panel');
    }

    function isOpen() {
        return !container.hidden;
    }

    function positionPanel(card) {
        var margin = 12;
        var rect = trigger.getBoundingClientRect();
        var width = Math.min(480, window.innerWidth - 2 * margin);
        var left = rect.right - width;
        if (left < margin) {
            left = margin;
        }
        if (left + width > window.innerWidth - margin) {
            left = window.innerWidth - margin - width;
        }
        card.style.top = rect.bottom + 10 + 'px';
        card.style.left = left + 'px';
    }

    function open() {
        container.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
        var card = panelCard();
        if (card) {
            positionPanel(card);
        }
        var close = container.querySelector('.stitch-panel-close');
        if (close) {
            close.focus();
        }
    }

    function close() {
        container.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
        trigger.focus();
    }

    trigger.addEventListener('click', function () {
        if (isOpen()) {
            close();
            return;
        }
        if (panelCard()) {
            open();
            return;
        }
        if (loading) {
            return;
        }
        loading = true;
        htmx.ajax('GET', '/stitches/panel', { target: container, swap: 'innerHTML' });
    });

    document.body.addEventListener('htmx:afterSwap', function (event) {
        if (event.detail.target !== container) {
            return;
        }
        loading = false;
        open();
    });

    ['htmx:responseError', 'htmx:sendError', 'htmx:timeout'].forEach(function (name) {
        document.body.addEventListener(name, function (event) {
            if (event.detail.target === container) {
                loading = false;
            }
        });
    });

    container.addEventListener('click', function (event) {
        if (event.target.closest('.stitch-panel-close')) {
            close();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && isOpen()) {
            close();
        }
    });

    window.addEventListener('resize', function () {
        var card = panelCard();
        if (isOpen() && card) {
            positionPanel(card);
        }
    });
})();
