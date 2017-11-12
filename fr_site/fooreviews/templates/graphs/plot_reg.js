
function plotREG(dataSeries, chartID, title){
    var chart =  {
                type: 'scatter'
        }
    var credits = {
                    enabled: true,
                    href: '//fooreviews.com',
                    text: 'fooreviews.com',
        }
    var xAxis = {
            min: -5,
            title: {
                enabled: true,
                text: 'Frequency'
            },
            startOnTick: true,
            endOnTick: true,
            showLastLabel: true
        }
    var yAxis =  {
            gridLineWidth: 0,
            title: {
                text: 'probs'
            }
        }
   var  plotOptions = {
            scatter: {
                marker: {
                    radius: 5,
                    states: {
                        hover: {
                            enabled: true,
                            lineColor: 'rgb(100,100,100)'
                        }
                    }
                },
                states: {
                    hover: {
                        marker: {
                            enabled: false
                        }
                    }
                }
                
            }
        }
    var tooltip =  {
                headerFormat: '{series.name}<br>',
                pointFormat: '<b>{point.label}</b>'
        }
    var legend =  {
            enabled: false,
        }
    var responsive =  {
            rules: [{
                condition: {
                    maxWidth: 400
                }
            }]
        }
    var series = [{
            name: 'Distribution',
            data: dataSeries,
            // color: '#000'
        }]
   
    Highcharts.chart(chartID, {
        chart,
        yAxis,
        xAxis,
        title,
        tooltip,
        credits,
        responsive,
        plotOptions,
        series,
        legend
        
});
}
function dataREG() {
    var dataSeries = {{ data_REG|safe }}
    var chartID = '{{ chartID_REG|safe }}'
    var title = {{ title_REG|safe }}
    plotREG(dataSeries, chartID, title)
   
    
}
dataREG()