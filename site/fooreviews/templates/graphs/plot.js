var credits = {   
                    enabled: false,
                    href: '//fooreviews.com',
                    text: 'Fooreviews.com',
                    position: {
                        y: 0,

                    }
                    // itemMarginBottom: 5,
                    // itemMarginTop: 5,
        }
 {%if metadata_page %}
 credits['enabled'] = true
 {%endif%}
var defaultStyle = {
                    fontFamily: "Arial",
                }
function plotDistro(dataSeries, chartID, title){

    title.margin = 50;
    var enableLabel = true,
        showInLegendResponsive = false,
        legendResponsive = false;
    if (windowSize <= 420){
        var pieSize = '90%',
            enableLabel = false,
            showInLegendResponsive = true,
            legendResponsive = true,
            labelFontSize = '10px',
            heightMax = '700px',
            widthMax = null;

    }
    else if (windowSize <= 520){
        var pieSize = '75%',
            labelFontSize = '8px',
            heightMax = '300px',
            widthMax = null;

    }
     else if (windowSize <= 768){
        var pieSize = '85%',
            labelFontSize = '9px',
            heightMax = '300px',
            widthMax = null;

    }
    else if (windowSize <= 992){
        var pieSize = '90%',
            labelFontSize = '9px',
            heightMax = '350px',
            widthMax = null;

    }
    else {
        var pieSize = '100%',
            labelFontSize = '12px',
            heightMax = '400px';

    }
    var chart =  {
                type: 'pie',
                spacingBottom: 15,
                width: widthMax,
                height: heightMax,
                style: defaultStyle,
                backgroundColor: null

        }
    var plotOptions =  {
                pie: {
                    shadow: false, 
                    center: ['50%', '50%'],
                    dataLabels: {
                            enabled: enableLabel,
                            formatter: function () {
                                return this.y > 0 ? this.point.name : null;
                            },
                    style: {
                            fontSize: labelFontSize,

                    }
                },
                showInLegend: showInLegendResponsive,


            }
        }
    var tooltip = {
                'headerFormat': '<span style="font-size:11px">{series.name}</span><br>',
                'pointFormat': '<span style="font-size:15px;color:{point.color}">{point.name}</span>: <b>{point.percentage:.1f}%</b>'
        }
    var series = [{
            name: 'Topic Distribution',
            data: dataSeries,
            size: pieSize,
            colorByPoint: true,
        }]
       
    var legend = {
            enabled: legendResponsive,
            layout: 'horizontal',
            align: 'center',
            verticalAlign: 'bottom',
            backgroundColor: null,
            borderWidth: 0,
            symbolRadius: 0,
            useHTML: true,
            itemMarginBottom: 10,
             labelFormatter: function () {
                return '<div style="width:180px; font-size:10px; font-weight: 400"><span style="float:left">' + this.name + ' </span><span style="float:right; margin-right:1%">' + (Math.round(this.percentage * 10) / 10).toFixed(0)  +  '%</span></div>';
            }
        }
    
    Highcharts.chart(chartID, {
        chart,
        title,
        tooltip,
        credits,
        plotOptions,
        series,
        legend,
        
});
}
function plotASR(dataSeries, chartID, title){
    title.margin = 30;
    var chart = {
            type: 'bubble',
            height: '500px',
            style: defaultStyle,
            backgroundColor: null,
            marginTop: 50,
        }
    var  yAxis =  {
                labels: {
                    enabled: true,
                },
               gridLineWidth: 0,
                tickLength: 1,
                tickInterval: 0.5,
                lineWidth: 0,
                max: 5.5,
                offset: 50,
                title: {
                    text: 'Rating',
                    margin: 25,

            }

        }
    var  xAxis =  {
                labels: {
                    enabled: true,
                },
                gridLineWidth: 0,
                tickLength: 0,
                lineWidth: 0,
                tickInterval: 5,
                offset: 30,
                min: 1,
                title: {
                    text: 'Aspect Rank',
                    margin: 25,
            }
        }
    var tooltip =  {
            useHTML: true,
            headerFormat: '<table>',
            pointFormat: '<tr><th colspan="2"><h6>{point.name}</h6></th></tr>' +
                '<tr><th>Rating:</th><td>{point.y:.1f}</td></tr>' +
                '<tr><th>Sentiment:</th><td>{point.sentiment}</td></tr>' +
                '<tr><th>Rank:</th><td>{point.x}</td></tr>' +
                '<tr><th style="padding-right:1em">Reliability:</th><td>{point.z}</td></tr>',
            footerFormat: '</table>',
            followPointer: true
    }
    var  plotOptions = {
            series: {
                dataLabels: {
                    enabled: false,
                    format: '{point.x}',
                    color: 'black',
                },
            }
        }
    var legend =  {
            enabled: false,
            backgroundColor: null,
        }

    var series = dataSeries
     Highcharts.chart(chartID, {
        chart,
        xAxis,
        yAxis,
        title,
        legend,
        tooltip,
        credits,
        plotOptions,
        series,

        
});

}

function plotTSR(dataSeries, chartID, title, dates) {
    var chart = {
            type: 'line',
            style: defaultStyle,
            backgroundColor: null,
        }
    var yAxis =  {
            title: {
                text: 'Number of Reviews',
                margin: 25,
            },
            gridLineWidth: 0,
     }
     var xAxis =  {
                categories: dates,
                tickInterval: {{TSR_interval}},
                title: {
                    text: 'Date of Submission',
                    margin: 25,
            },
            }


    var tooltip = {
                'headerFormat': '<span style="font-size:12px">Rating: {series.name}</span><br><span style="font-size:12px">Date: {point.x}</span><br>',
                'pointFormat': '<span style="font-size:15px;color:{point.color}">Number of Reviews</span>: <b>{point.y}</b>'
    }
     var legend =  {
            enabled: true,
            layout: 'vertical',
            align: 'right',
            verticalAlign: 'middle',
            useHTML: true,
            symbolWidth: 25,
            backgroundColor: null,
            // itemMarginBottom: 5,
            // itemMarginTop: -5,
            itemStyle: {
                lineHeight: '18px'
            },
            labelFormatter: function() {
                var icon = '<span class="ion-android-star" style="font-size:16px; color: orange; padding-left:5px;"></span>'
                if (this.name != 'Overall'){
                    var starRating = icon + ' '
                    for (i=0; i < this.name-1; i +=1){
                        starRating +=  icon + ' '
                    }
                    return starRating;
                }
                name = '<span class="overal-review-count" style="font-size:12px; color: orange; padding-left:5px;" >Overall</span>'
                return name;
        }
    }
    var plotOptions = {
            series: {
                lineWidth: 2,
                marker: {
                    enabled: false,
                }
            }
    }
    var series = dataSeries

    Highcharts.chart(chartID, {
        chart,
        xAxis,
        yAxis,
        title,
        legend,
        tooltip,
        credits,
        plotOptions,
        series,

        
});

}
function updateLegend(legend, title){
     if (windowSize >= 992){
        if (title.text.indexOf("Star") != -1 || title.text.indexOf("Classification") != -1){
            legend.layout = 'vertical'
            legend.align = 'right'
            legend.verticalAlign = 'middle' 
        }
    }
    return legend
}
function updateHeight(chart, title){
     if (windowSize >= 992){
        if (title.text.indexOf("Star") != -1 || title.text.indexOf("Classification") != -1){
            chart.height = '240px' 
        }
    }
    return chart

}
function getCellWidth(title){
    var cellWidth = '120px';
    var pieSize = '80%'
    if (title.text.indexOf("Verified") != -1){
        cellWidth = '100px'
    }
    else if (title.text.indexOf("Star") != -1){
        cellWidth = '90px'
        if (windowSize <= 320){
            pieSize = '100%'
            cellWidth = '100px'
        }
        else if (windowSize <= 420){
            cellWidth = '90px'
        }
        else if (windowSize <= 576){
            cellWidth = '120px'
        }
    }
    // else if (title.text.indexOf("Helpful") != -1){
    //     cellWidth = '120px'
    // }
    else if (title.text.indexOf("ecommendation") != -1){
        cellWidth = '180px'
    }
    else if (title.text.indexOf("Classification") != -1){
        if (windowSize <= 320){
            cellWidth = '100px'
        }
        else if (windowSize <= 420){
            cellWidth = '120px'
        }
         else if (windowSize <= 768){
            pieSize = '100%'
        }
    }
   
    return [cellWidth, pieSize]
}

function plotDonut(dataSeries, chartID, title){
    var enableLabel = false,
        pieSize = '80%',
        showInLegendResponsive = true,
        legendResponsive = true,
        heightMax = '400px',
        widthMax = null,
        labelDistance = 0,
        labelFontSize = '12px',
        titleFontSize = '16px',
        legendFontSize = '12px',
        alignResponsive = 'center'
        verticalAlignResponsive = 'bottom',
        labelDistance = 30;
  
    var paramArray = getCellWidth(title),
        cellWidth = paramArray[0],
        pieSize = paramArray[1]; 

    var chart =  {
                type: 'pie',
                height: heightMax,
                width: widthMax,
                spacingBottom: 5,
                style: defaultStyle,
                backgroundColor: null,
        }
    var plotOptions =  {
                pie: {
                    shadow: false, 
                    center: ['50%', '50%'],
                    dataLabels: {
                            enabled: enableLabel,
                            formatter: function () {
                                return this.y > 0 ? this.point.name : null;
                            },
                    style: {
                            fontSize: labelFontSize,
                    },
                    distance: labelDistance,
                },
                showInLegend: showInLegendResponsive,


            }
        }
    var tooltip = {
                'headerFormat': '<span style="font-size:13px">{series.name}</span><br></span><br>',
                'pointFormat': '<span style="font-size:11px">{point.header}: {point.yString}</span><br><span style="font-size:15px;color:{point.color}">{point.name}</span>: <b>{point.percentage:.1f}%</b>'
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
            size: pieSize,
            innerSize: '70%',
            style: {
                            fontSize: '1px',
                    },
        }]
    var legend = {
            enabled: legendResponsive,
            symbolRadius: 0,
            layout: 'vertical',
            align: alignResponsive,
            verticalAlign: verticalAlignResponsive,
            backgroundColor: null,
            borderWidth: 0,
            useHTML: true,
            itemMarginBottom: 5,
            itemMarginTop: 5,
             labelFormatter: function () {
                return '<div style="width:' + cellWidth + '; font-size:'+legendFontSize + '; font-weight: 100"><span style="float:left">' + this.name + '</span><span style="float:right; margin-left:10%">' + (Math.round(this.percentage * 10) / 10).toFixed(0) +  '%</span></div>';
            }
        }
   
    title.style = {
            fontSize: '14px;',
            fontWeight: '300',
    }
    legend = updateLegend(legend, title)
    chart = updateHeight(chart, title)
    Highcharts.chart(chartID, {
        chart,
        title,
        tooltip,
        credits,
        responsive,
        plotOptions,
        series,
        legend,
        
});
}

