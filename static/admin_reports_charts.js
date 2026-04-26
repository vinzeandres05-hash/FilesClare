document.addEventListener("DOMContentLoaded", function() {
    // --- COLOR MAPPING LOGIC ---
    const statusColorMap = {
        'Pending': '#ffc107',          // Yellow
        'Processing': '#fd7e14',       // Orange
        'Accepted': '#2cc5ad',         // EduDash Teal
        'Ready for pickup': '#0dcaf0',   // Cyan
        'Rejected': '#ff4d4d',         // Red
        'Completed': '#a0a4b8'         // Gray
    };

    // Global Font Settings
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.color = '#a0a4b8';

    // 1. BAR CHART SETUP (Monthly Volume)
    const ctxBar = document.getElementById('barChartReport');
    if (ctxBar) {
        new Chart(ctxBar, {
            type: 'bar',
            data: {
                labels: barLabels, 
                datasets: [{
                    label: 'Requests',
                    data: barCounts,
                    backgroundColor: 'rgba(44, 197, 173, 0.2)', // Light Teal fill
                    borderColor: '#2cc5ad', // Solid Teal border
                    borderWidth: 2,
                    borderRadius: 5, // Rounded corners para modern
                    hoverBackgroundColor: '#2cc5ad',
                    barPercentage: 0.5,
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
                            color: '#f8f9fa' 
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)', // Malinaw na grid line
                            drawBorder: false
                        }
                    },
                    x: {
                        ticks: { color: '#f8f9fa' },
                        grid: { display: false } // Mas malinis tignan pag walang vertical lines
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#1f2235',
                        titleColor: '#2cc5ad',
                        bodyColor: '#fff',
                        borderColor: '#2cc5ad',
                        borderWidth: 1,
                        padding: 10,
                        displayColors: false
                    }
                }
            }
        });
    }

    // 2. PIE CHART SETUP (Status Distribution)
    const ctxPie = document.getElementById('pieChartReport');
    if (ctxPie) {
        const pieBackgrounds = pieLabels.map(label => statusColorMap[label] || '#0d6efd');

        new Chart(ctxPie, {
            type: 'pie',
            data: {
                labels: pieLabels,
                datasets: [{
                    data: pieCounts,
                    backgroundColor: pieBackgrounds,
                    borderWidth: 3,
                    borderColor: '#1a1d29', // Space/gap effect between slices
                    hoverOffset: 15
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 25,
                            usePointStyle: true,
                            pointStyle: 'circle',
                            color: '#f8f9fa',
                            font: { 
                                size: 12,
                                weight: '500'
                            }
                        }
                    },
                    tooltip: {
                        backgroundColor: '#1f2235',
                        padding: 12,
                        bodyFont: { size: 14 },
                        callbacks: {
                            label: function(context) {
                                let label = context.label || '';
                                let value = context.raw || 0;
                                let total = context.dataset.data.reduce((a, b) => a + b, 0);
                                let percentage = Math.round((value / total) * 100);
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }
});