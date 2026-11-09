(function () {
    const statusEl = document.getElementById('challenge-status');

    if (!statusEl) {
        return;
    }

    const params = new URLSearchParams(window.location.search);
    const currentPath = window.location.pathname + window.location.search + window.location.hash;
    const requestedNext = params.get('next') || (window.location.pathname.startsWith('/challenge') ? '/' : currentPath);
    const nextPath = requestedNext.startsWith('/') && !requestedNext.startsWith('//') && !requestedNext.startsWith('/challenge')
        ? requestedNext
        : '/';

    function setStatus(text) {
        statusEl.textContent = text;
    }

    async function sha256Hex(input) {
        const bytes = new TextEncoder().encode(input);
        const hash = await crypto.subtle.digest('SHA-256', bytes);
        return Array.from(new Uint8Array(hash)).map((byte) => byte.toString(16).padStart(2, '0')).join('');
    }

    async function solvePow(token, difficulty) {
        const prefix = '0'.repeat(difficulty);

        for (let counter = 0; counter < 250000; counter++) {
            const proof = counter.toString(36);
            const digest = await sha256Hex(token + ':' + proof);

            if (digest.startsWith(prefix)) {
                return proof;
            }
        }

        throw new Error('check-timeout');
    }

    async function runChallenge() {
        if (!window.crypto || !crypto.subtle) {
            throw new Error('browser-crypto');
        }

        document.cookie = 'eclipse_blog_cookie_test=1; path=/; SameSite=Lax';
        const cookiesEnabled = document.cookie.indexOf('eclipse_blog_cookie_test=1') !== -1;

        try {
            localStorage.setItem('eclipse_blog_storage_test', '1');
            localStorage.removeItem('eclipse_blog_storage_test');
        } catch (error) {}

        setStatus('Checking browser');

        const issued = await fetch('/verify.php?action=challenge', {
            credentials: 'same-origin',
            cache: 'no-store',
            headers: { Accept: 'application/json' },
        });

        if (!issued.ok) {
            throw new Error('challenge-issue');
        }

        const challenge = await issued.json();
        setStatus('Completing check');

        const proof = await solvePow(challenge.token, challenge.difficulty || 3);
        const verified = await fetch('/verify.php', {
            method: 'POST',
            credentials: 'same-origin',
            cache: 'no-store',
            headers: {
                'Content-Type': 'application/json',
                Accept: 'application/json',
            },
            body: JSON.stringify({
                token: challenge.token,
                proof,
                checks: {
                    cookies: cookiesEnabled,
                    webdriver: navigator.webdriver === true,
                    language: navigator.language || '',
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || '',
                    width: screen.width || 0,
                    height: screen.height || 0,
                },
            }),
        });

        if (!verified.ok) {
            throw new Error('verify-failed');
        }

        setStatus('Do not reload the page, you will be automatically redirected');
        window.setTimeout(() => window.location.replace(nextPath), 3000);
    }

    runChallenge().catch(() => {
        setStatus('Refresh the page to try again');
    });
})();
