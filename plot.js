
<script>
var graph;
graph = new Rickshaw.Graph.Ajax( {
  	element: document.querySelector("#chart"),
  	width: 800, height: 200, renderer: "line", interpolation: "linear",
  	dataURL: "data.json",
    series: [{name:"Mean Displacement", color:"#c05020"}],
    onComplete: function(transport) {
        var graph = transport.graph;
        var detail = new Rickshaw.Graph.HoverDetail({
            graph: graph,
            xFormatter: function(x) { return x + " seconds" },
            yFormatter: function(y) { return y + " mm" },
        });
        var x_axis = new Rickshaw.Graph.Axis.X({
            graph: graph,
        });
        x_axis.graph.update();
        var y_axis = new Rickshaw.Graph.Axis.Y({
            graph: graph,
            tickFormat: Rickshaw.Fixtures.Number.formatKMBT,
        });
        y_axis.graph.update();
        var slider = new Rickshaw.Graph.RangeSlider({
            graph: graph,
            element: document.querySelector("#slider"),
        });
        //slider.graph.update();
    }
});
</script>

