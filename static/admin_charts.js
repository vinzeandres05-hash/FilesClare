document.addEventListener("DOMContentLoaded", function() {
    // --- COLOR MAPPING LOGIC ---
    const statusColorMap = {
        'Pending': '#ffc107',          
        'Processing': '#fd7e14',       
        'Accepted': '#2cc5ad',         // EduDash Teal
        'Ready for pickup': '#0dcaf0',   
        'Rejected': '#ff4d4d',         
        'Completed': '#a0a4b8'         
    };

    // Global Font Settings para sa lahat ng Charts
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.color = '#a0a4b8'; // Light gray text para sa labels

    // 1. BAR CHART SETUP
    const ctxBar = document.getElementById('barChart');
    if (ctxBar) {
        new Chart(ctxBar, {
            type: 'bar',
            data: {
                labels: barLabels, 
                datasets: [{
                    label: 'Number of Requests',
                    data: barCounts,
                    backgroundColor: 'rgba(44, 197, 173, 0.8)', // Teal with slight transparency
                    borderColor: '#2cc5ad', // Solid Teal Border
                    borderWidth: 2,
                    borderRadius: 6, // Rounder bars for modern look
                    barPercentage: 0.4,
                    categoryPercentage: 0.5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { 
                        beginAtZero: true,
                        ticks: { 
                            stepSize: 1,
                            color: '#f8f9fa' // Pinalinaw na numbers sa gilid
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.15)', // PINALINAW NA LINE
                            drawBorder: false
                        }
                    },
                    x: {
                        ticks: { 
                            color: '#f8f9fa' // Pinalinaw na labels sa ilalim
                        },
                        grid: {
                            display: false // Inalis ang vertical lines para malinis
                        }
                    }
                },
                plugins: {
                    legend: {
                        labels: {
                            color: '#f8f9fa',
                            font: { weight: '600' }
                        }
                    }
                }
            }
        });
    }

    // 2. PIE CHART SETUP
    const ctxPie = document.getElementById('pieChart');
    if (ctxPie) {
        const pieBackgrounds = pieLabels.map(label => statusColorMap[label] || '#0d6efd');

        new Chart(ctxPie, {
            type: 'pie',
            data: {
                labels: pieLabels,
                datasets: [{
                    data: pieCounts,
                    backgroundColor: pieBackgrounds,
                    borderColor: '#1f2235', // Match sa background para sa "gap" effect
                    borderWidth: 3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 20,
                            usePointStyle: true,
                            color: '#f8f9fa', // Pinalinaw na legend labels
                            font: { size: 12 }
                        }
                    }
                }
            }
        });
    }
});