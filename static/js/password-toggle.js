document.querySelectorAll('.password-toggle').forEach((button) => {
    const input = document.getElementById(button.getAttribute('aria-controls'));
    if (!input) return;

    const label = input.labels[0].textContent.trim().toLowerCase();
    button.addEventListener('click', () => {
        const showPassword = input.type === 'password';
        input.type = showPassword ? 'text' : 'password';
        button.setAttribute('aria-pressed', String(showPassword));
        button.setAttribute('aria-label', `${showPassword ? 'Hide' : 'Show'} ${label}`);
    });
});
