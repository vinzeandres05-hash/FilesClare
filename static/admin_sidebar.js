document.addEventListener('DOMContentLoaded', function() {
    // Finds all main menu headers (h3) in the admin sidebar
    const menuHeaders = document.querySelectorAll('.admin-sidebar-menu h3');

    menuHeaders.forEach(header => {
        
        // Add a click event listener to the h3 header
        header.addEventListener('click', function(e) {
            
            // Toggle visibility of sub-links until the next h3 is encountered
            let current = header.nextElementSibling;
            let isVisible = current && current.style.display !== 'none';
            
            // Check if the next sibling is a sub-link container
            if (current && current.classList.contains('sub-link')) {
                
                while (current && !current.matches('h3')) {
                    if (current.classList.contains('sub-link')) {
                         current.style.display = isVisible ? 'none' : 'block';
                    }
                    current = current.nextElementSibling;
                }
            }
        });

        // Initial state: Collapse all sub-links unless one is active
        let current = header.nextElementSibling;
        let hasActiveSubLink = false;

        // Check if any sub-link is active
        while (current && !current.matches('h3')) {
            if (current.classList.contains('active')) {
                hasActiveSubLink = true;
                break;
            }
            current = current.nextElementSibling;
        }

        // Collapse all sub-links if no sub-link is active
        if (!hasActiveSubLink) {
             let collapseCurrent = header.nextElementSibling;
             while (collapseCurrent && !collapseCurrent.matches('h3')) {
                if (collapseCurrent.classList.contains('sub-link')) {
                    collapseCurrent.style.display = 'none';
                }
                collapseCurrent = collapseCurrent.nextElementSibling;
             }
        }
    });
});